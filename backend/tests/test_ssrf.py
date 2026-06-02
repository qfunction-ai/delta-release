"""Tests for SSRF protection — URL validation and IP checking."""

from unittest.mock import patch

from app.ssrf import (
    _is_github_domain,
    _is_private_ip,
    pin_url,
    validate_api_url,
    validate_download_url,
)


class TestIsPrivateIp:
    """Tests for _is_private_ip."""

    def test_loopback(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_private_10(self):
        assert _is_private_ip("10.0.0.1") is True

    def test_private_172(self):
        assert _is_private_ip("172.16.0.1") is True

    def test_private_192(self):
        assert _is_private_ip("192.168.1.1") is True

    def test_link_local(self):
        assert _is_private_ip("169.254.1.1") is True

    def test_ipv6_loopback(self):
        assert _is_private_ip("::1") is True

    def test_public_ip(self):
        assert _is_private_ip("8.8.8.8") is False

    def test_invalid_ip(self):
        assert _is_private_ip("not-an-ip") is True


class TestValidateApiUrl:
    """Tests for validate_api_url."""

    def test_empty_url(self):
        is_valid, error, ip = validate_api_url("")
        assert is_valid is True

    def test_localhost_blocked(self):
        is_valid, error, ip = validate_api_url("http://localhost/api")
        assert is_valid is False
        assert "Localhost" in error

    def test_ftp_scheme_blocked(self):
        is_valid, error, ip = validate_api_url("ftp://example.com/file")
        assert is_valid is False
        assert "scheme" in error

    def test_no_hostname(self):
        is_valid, error, ip = validate_api_url("http:///path")
        assert is_valid is False
        assert "hostname" in error

    def test_public_url(self):
        """Public URL should pass validation (DNS resolution may fail in CI)."""
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            is_valid, error, ip = validate_api_url("https://example.com/api")
        assert is_valid is True
        assert ip == "93.184.216.34"

    def test_private_ip_blocked(self):
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("10.0.0.1", 0))]
            is_valid, error, ip = validate_api_url("https://internal.corp/api")
        assert is_valid is False
        assert "private" in error.lower()

    def test_dns_failure(self):
        import socket

        with patch("socket.getaddrinfo", side_effect=socket.gaierror("DNS failed")):
            is_valid, error, ip = validate_api_url("https://nonexistent.example.com/api")
        assert is_valid is False
        assert "resolve" in error.lower()


class TestPinUrl:
    """Tests for pin_url."""

    def test_pins_ip_http(self):
        """For HTTP URLs, the hostname is replaced with the pinned IP."""
        url, headers = pin_url("http://example.com/path", "93.184.216.34")
        assert "93.184.216.34" in url
        assert headers["Host"] == "example.com"

    def test_preserves_url_https(self):
        """For HTTPS URLs, the original URL is preserved (TLS cert validation needs the real hostname)."""
        url, headers = pin_url("https://example.com/path", "93.184.216.34")
        assert url == "https://example.com/path"
        assert headers == {}  # No Host header needed — URL is unchanged

    def test_preserves_port_http(self):
        url, headers = pin_url("http://example.com:8080/path", "93.184.216.34")
        assert ":8080" in url
        assert headers["Host"] == "example.com"

    def test_preserves_port_https(self):
        """HTTPS with port preserves the original URL."""
        url, headers = pin_url("https://example.com:8443/path", "93.184.216.34")
        assert url == "https://example.com:8443/path"
        assert headers == {}

    def test_no_hostname(self):
        url, headers = pin_url("http:///path", "1.2.3.4")
        assert headers == {}


class TestIsGithubDomain:
    """Tests for _is_github_domain."""

    def test_github_com(self):
        assert _is_github_domain("github.com") is True

    def test_raw_githubusercontent(self):
        assert _is_github_domain("raw.githubusercontent.com") is True

    def test_subdomain(self):
        assert _is_github_domain("something.github.com") is True

    def test_non_github(self):
        assert _is_github_domain("evil.com") is False

    def test_case_insensitive(self):
        assert _is_github_domain("GitHub.com") is True


class TestValidateDownloadUrl:
    """Tests for validate_download_url."""

    def test_empty_url(self):
        is_valid, error, ip = validate_download_url("")
        assert is_valid is True

    def test_github_domain(self):
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("140.82.121.3", 0))]
            is_valid, error, ip = validate_download_url("https://github.com/user/repo/archive/main.zip")
        assert is_valid is True

    def test_non_github_domain_blocked(self):
        is_valid, error, ip = validate_download_url("https://evil.com/malware")
        assert is_valid is False
        assert "GitHub domain" in error

    def test_ftp_scheme_blocked(self):
        is_valid, error, ip = validate_download_url("ftp://github.com/file")
        assert is_valid is False
