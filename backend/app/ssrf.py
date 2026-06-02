"""SSRF protection — URL validation for outbound requests.

Validates that user-supplied URLs do not target private/reserved IP ranges
or dangerous schemes before the server makes outbound HTTP requests.
"""

import ipaddress
import socket
from urllib.parse import urlparse

# Private/reserved IP ranges that should never be targeted by user-controlled requests
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("10.0.0.0/8"),  # Private (RFC 1918)
    ipaddress.ip_network("172.16.0.0/12"),  # Private (RFC 1918)
    ipaddress.ip_network("192.168.0.0/16"),  # Private (RFC 1918)
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local (cloud metadata)
    ipaddress.ip_network("0.0.0.0/8"),  # "This network"
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT (RFC 6598)
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmarking (RFC 2544)
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

_ALLOWED_SCHEMES = {"http", "https"}


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address falls within any blocked network."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # Treat unparseable IPs as private (fail closed)

    for network in _BLOCKED_NETWORKS:
        if ip in network:
            return True
    return False


def _validate_url_ip(hostname: str) -> tuple[bool, str, str]:
    """Resolve hostname and validate all IPs are public.

    Returns (is_valid, error_message, resolved_ip). The resolved_ip
    should be used to pin the connection IP (prevents DNS rebinding).
    """
    resolved_ip = ""
    try:
        addr_infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        for family, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            if _is_private_ip(ip_str):
                return False, f"URL resolves to a private/reserved IP address ({ip_str})", ""
            if not resolved_ip:
                resolved_ip = ip_str
    except socket.gaierror:
        return False, f"Could not resolve hostname '{hostname}'", ""
    except (socket.herror, socket.timeout, OSError) as e:
        return False, f"Could not validate hostname '{hostname}': {type(e).__name__}", ""
    return True, "", resolved_ip


def validate_api_url(url: str) -> tuple[bool, str, str]:
    """Validate that a URL is safe for outbound server-side requests.

    Returns (is_valid, error_message, resolved_ip). If is_valid is False,
    the URL should not be used for any outbound request. The resolved_ip
    should be used to pin the connection IP (prevents DNS rebinding).

    Callers should use the resolved_ip to construct the request URL and
    set the Host header to the original hostname:
        response = await client.get(f"http://{resolved_ip}/path", headers={"Host": hostname})
    """
    if not url:
        return True, "", ""  # Empty URLs are handled by the caller (required-field checks)

    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "Invalid URL format", ""

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False, f"URL scheme '{parsed.scheme}' is not allowed. Use http:// or https://", ""

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must include a hostname", ""

    # Block obvious private hostnames
    if hostname in ("localhost", "localhost.localdomain"):
        return False, "Localhost URLs are not allowed", ""

    # Resolve and validate IPs
    return _validate_url_ip(hostname)


def pin_url(url: str, resolved_ip: str) -> tuple[str, dict[str, str]]:
    """Construct a pinned URL and Host header from a validated IP address.

    For HTTP URLs, replaces the hostname with the resolved IP to prevent
    DNS rebinding attacks. The original hostname is sent in the Host header.

    For HTTPS URLs, the hostname is NOT replaced in the URL because TLS
    certificate validation checks the hostname in the URL against the
    certificate's CN/SAN. Replacing it with an IP would cause a
    CERTIFICATE_VERIFY_FAILED error. Instead, the caller should use
    httpx's transport-level pinning (see create_pinned_transport).

    Returns (url, headers) where headers includes at least
    {"Host": original_hostname} for HTTP URLs, or {} for HTTPS URLs.

    Usage:
        is_valid, error, resolved_ip = validate_download_url(url)
        if not is_valid:
            raise ...
        pinned_url, headers = pin_url(url, resolved_ip)
        resp = await client.get(pinned_url, headers={**headers, "User-Agent": "Delta-App"})
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return url, {}

    # For HTTPS, keep the original URL intact — TLS cert validation needs
    # the real hostname. The caller should pin the IP at the transport level.
    if parsed.scheme == "https":
        return url, {}

    # For HTTP, replace hostname with the pinned IP to prevent DNS rebinding
    if parsed.port:
        netloc = f"{resolved_ip}:{parsed.port}"
    else:
        netloc = resolved_ip

    pinned = parsed._replace(netloc=netloc).geturl()
    return pinned, {"Host": hostname}


def create_pinned_transport(resolved_ip: str):
    """Create an httpx transport that pins connections to a specific IP.

    This provides DNS rebinding protection for HTTPS URLs without breaking
    TLS certificate validation. The transport replaces the hostname in the
    URL with the pinned IP and sets the `sni_hostname` extension so that
    TLS SNI and certificate validation use the original hostname.

    Unlike the previous global-socket-patching approach, this is safe under
    concurrent requests because it doesn't touch any global state.

    Usage:
        is_valid, error, resolved_ip = validate_download_url(url)
        if not is_valid:
            raise ...
        transport = create_pinned_transport(resolved_ip)
        async with httpx.AsyncClient(transport=transport) as client:
            resp = await client.get(url)
    """
    import httpx

    _pinned_ip = resolved_ip

    class PinnedDNSTransport(httpx.AsyncBaseTransport):
        """Transport that pins connections to a specific IP.

        Rewrites the request URL to use the pinned IP instead of the
        original hostname, and sets the sni_hostname extension so TLS
        still validates against the original hostname.
        """

        def __init__(self, pinned_ip: str):
            self._pinned_ip = pinned_ip
            self._inner = httpx.AsyncHTTPTransport()

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            # Rewrite URL: replace hostname with pinned IP, preserve port
            original_url = request.url
            port = original_url.port
            original_hostname = original_url.host

            # Reconstruct URL with pinned IP
            pinned_url = original_url.copy_with(host=self._pinned_ip, port=port)

            pinned_request = httpx.Request(
                method=request.method,
                url=pinned_url,
                headers=request.headers,
                content=request.content,
                extensions={
                    **request.extensions,
                    "sni_hostname": original_hostname,
                },
            )

            return await self._inner.handle_async_request(pinned_request)

        async def aclose(self) -> None:
            await self._inner.aclose()

    return PinnedDNSTransport(_pinned_ip)


# Domains allowed for GitHub asset downloads (after validating the initial
# GitHub URL, asset download_url values are checked against this list)
_GITHUB_DOMAINS = {
    "github.com",
    "api.github.com",
    "raw.githubusercontent.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
    "avatars.githubusercontent.com",
    "user-images.githubusercontent.com",
}


def _is_github_domain(hostname: str) -> bool:
    """Check if a hostname is a known GitHub domain or subdomain thereof."""
    hostname = hostname.lower()
    if hostname in _GITHUB_DOMAINS:
        return True
    for domain in _GITHUB_DOMAINS:
        if hostname.endswith(f".{domain}"):
            return True
    return False


def validate_download_url(url: str) -> tuple[bool, str, str]:
    """Validate a download URL returned by the GitHub API.

    GitHub API responses include download_url fields that are attacker-controlled
    (a malicious repo author can set these to any URL). This function ensures
    that such URLs point to known GitHub domains AND resolve to non-private IPs.

    Returns (is_valid, error_message, resolved_ip) same as validate_api_url.
    """
    if not url:
        return True, "", ""

    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "Invalid URL format", ""

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False, f"URL scheme '{parsed.scheme}' is not allowed", ""

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must include a hostname", ""

    # Restrict to known GitHub domains
    if not _is_github_domain(hostname):
        return False, f"Download URL hostname '{hostname}' is not a known GitHub domain", ""

    # Resolve and validate IPs
    return _validate_url_ip(hostname)
