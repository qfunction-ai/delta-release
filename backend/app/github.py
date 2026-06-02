"""Shared GitHub URL parsing and API utilities.

Used by both skills and tools GitHub fetch flows.
"""

import re
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status


def parse_github_url(url: str) -> tuple[str, str, str | None, str]:
    """Parse a GitHub URL into (owner, repo, branch, sub_path).

    Supported formats:
    - https://github.com/user/repo/tree/branch/path/to/dir
    - https://github.com/user/repo (root of repo)
    """
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+)(?:/(.+))?)?", url.rstrip("/"))
    if not match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GitHub URL. Use format: https://github.com/user/repo/tree/branch/path",
        )
    return match.group(1), match.group(2), match.group(3), match.group(4) or ""


def build_github_headers() -> dict:
    """Return standard headers for GitHub API requests."""
    return {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Delta-App",
    }


async def detect_default_branch(
    client_http,
    owner: str,
    repo: str,
    gh_headers: dict,
) -> str:
    """Detect the default branch of a GitHub repo. Falls back to 'main'."""
    repo_resp = await client_http.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=gh_headers,
    )
    if repo_resp.status_code == 200:
        return repo_resp.json().get("default_branch", "main")
    return "main"


async def fetch_github_directory(
    client_http,
    owner: str,
    repo: str,
    branch: str,
    sub_path: str,
    gh_headers: dict,
) -> list[dict]:
    """Fetch directory contents from the GitHub API.

    Returns a list of entry dicts. Raises HTTPException on rate limit or
    failure. If the URL points to a single file, wraps it in a list.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{sub_path}"
    params = {"ref": branch}

    response = await client_http.get(api_url, params=params, headers=gh_headers)

    if response.status_code == 403 and "rate limit" in response.text.lower():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub API rate limit exceeded. Try again later or use upload instead.",
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to fetch GitHub repository: {response.status_code}"
        )

    contents = response.json()

    # If it's a single file (not a directory), wrap it
    if isinstance(contents, dict) and contents.get("type") == "file":
        contents = [contents]

    if not isinstance(contents, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub URL must point to a directory")

    return contents


async def _fetch_github_resource(
    client_http,
    download_url: str,
    description: str,
) -> httpx.Response:
    """Fetch a resource from GitHub with SSRF protection.

    Validates the download URL against SSRF, pins the connection to the
    resolved IP, and returns the raw httpx.Response.

    Args:
        client_http: An httpx.AsyncClient instance.
        download_url: The URL to download the resource from.
        description: Human-readable name for error messages (e.g., "SKILL.md").

    Returns:
        The httpx.Response object.
    """
    from app.ssrf import create_pinned_transport, pin_url, validate_download_url

    is_valid, error, resolved_ip = validate_download_url(download_url)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid download URL for {description}: {error}"
        )

    # Pin the connection to the validated IP to prevent DNS rebinding
    pinned_url, pin_headers = pin_url(download_url, resolved_ip)

    # For HTTPS URLs, use a pinned transport so TLS cert validation uses
    # the original hostname but the connection goes to the validated IP.
    # For HTTP URLs, pin_url already replaced the hostname in the URL.
    parsed = urlparse(download_url)
    if parsed.scheme == "https":
        transport = create_pinned_transport(resolved_ip)
        async with httpx.AsyncClient(transport=transport, timeout=client_http.timeout) as pinned_client:
            resp = await pinned_client.get(
                download_url,
                headers={**pin_headers, "User-Agent": "Delta-App"},
            )
    else:
        resp = await client_http.get(
            pinned_url,
            headers={**pin_headers, "User-Agent": "Delta-App"},
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to download {description} from GitHub"
        )

    return resp


async def fetch_file_from_github(
    client_http,
    download_url: str,
    description: str,
    max_size: int,
) -> str:
    """Fetch a single file from GitHub with SSRF protection.

    Args:
        client_http: An httpx.AsyncClient instance.
        download_url: The URL to download the file from.
        description: Human-readable name for error messages (e.g., "SKILL.md").
        max_size: Maximum allowed file size in bytes.

    Returns:
        The file content as a string.
    """
    resp = await _fetch_github_resource(client_http, download_url, description)
    if len(resp.text) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{description} from GitHub exceeds maximum size of {max_size // (1024 * 1024)}MB",
        )
    return resp.text


async def fetch_file_bytes_from_github(
    client_http,
    download_url: str,
    description: str,
    max_size: int,
) -> bytes:
    """Fetch a single file from GitHub with SSRF protection (binary-safe).

    Same as fetch_file_from_github but returns raw bytes instead of text.
    Use this for files that may be binary (images, PDFs, etc.).

    Args:
        client_http: An httpx.AsyncClient instance.
        download_url: The URL to download the file from.
        description: Human-readable name for error messages.
        max_size: Maximum allowed file size in bytes.

    Returns:
        The file content as bytes.
    """
    resp = await _fetch_github_resource(client_http, download_url, description)
    if len(resp.content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{description} from GitHub exceeds maximum size of {max_size // (1024 * 1024)}MB",
        )
    return resp.content


async def fetch_github_subdir_contents(
    client_http,
    subdir_url: str,
    params: dict,
    gh_headers: dict,
) -> list[dict] | None:
    """Fetch a subdirectory listing from GitHub API. Returns None on failure.

    Validates the subdir_url is a known GitHub API domain to prevent SSRF
    via malicious GitHub API responses that could redirect to internal URLs.
    """
    from urllib.parse import urlparse

    from app.ssrf import _is_github_domain

    try:
        parsed = urlparse(subdir_url)
        if not _is_github_domain(parsed.hostname or ""):
            return None
    except ValueError:
        return None

    resp = await client_http.get(subdir_url, params=params, headers=gh_headers)
    if resp.status_code != 200:
        return None
    contents = resp.json()
    if not isinstance(contents, list):
        return None
    return contents
