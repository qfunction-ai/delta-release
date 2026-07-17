"""Integration tests for docs fetch routes — _do_fetch_docs endpoint behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_httpx_response(
    text: str = "<html><body><p>API Reference</p></body></html>",
    content_type: str = "text/html",
    status_code: int = 200,
    url: str = "https://falconpy.readthedocs.io/en/latest/Hosts.html",
    headers: dict | None = None,
):
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.content = text.encode("utf-8")
    resp.headers = {"content-type": content_type}
    resp.url = url
    if headers:
        resp.headers.update(headers)
    return resp


def _mock_async_client(responses: list):
    """Build a mock httpx.AsyncClient that returns the given responses in order.

    Each call to client.get() returns the next response in the list.
    """
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    call_count = 0

    async def _get(url, **kwargs):
        nonlocal call_count
        if call_count < len(responses):
            resp = responses[call_count]
            call_count += 1
            return resp
        return responses[-1]

    client.get = _get
    return client


@pytest.mark.asyncio
class TestDocsFetchRoutes:
    """Integration tests for /api/docs/fetch endpoint."""

    async def test_fetch_returns_untrusted_content_marker(self, registered_client, mock_letta_client):
        """Fetched content is wrapped in EXTERNAL DOCUMENTATION delimiters."""
        client, headers, _ = registered_client

        # Enable agent_tool_creation (which enables both propose_tool and fetch_docs)
        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"agent_tool_creation": True},
        )
        assert resp.status_code == 200

        mock_resp = _mock_httpx_response(
            text="<html><body><p>HostsAPI.query_devices(limit=100)</p></body></html>",
            content_type="text/html",
        )
        mock_client = _mock_async_client([mock_resp])

        with (
            patch("app.docs.routes.validate_docs_url", return_value=(True, "", "1.2.3.4")),
            patch("app.docs.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            resp = await client.post(
                "/api/docs/fetch",
                headers=headers,
                json={"url": "https://falconpy.readthedocs.io/en/latest/Hosts.html", "package": "crowdstrike-falconpy"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "--- EXTERNAL DOCUMENTATION" in data["content"]
        assert "--- END EXTERNAL DOCUMENTATION ---" in data["content"]
        assert "untrusted" in data["content"].lower()
        assert "HostsAPI.query_devices" in data["content"]

    async def test_fetch_disabled_returns_403(self, registered_client, mock_letta_client):
        """When agent_tool_creation is False, the endpoint returns 403."""
        client, headers, _ = registered_client

        # agent_tool_creation defaults to False, no need to set it

        resp = await client.post(
            "/api/docs/fetch",
            headers=headers,
            json={"url": "https://falconpy.readthedocs.io/en/latest/Hosts.html"},
        )

        assert resp.status_code == 403
        assert "disabled" in resp.json()["detail"].lower()

    async def test_fetch_blocked_domain_returns_400(self, registered_client, mock_letta_client):
        """When the domain is not in the allowlist, the endpoint returns 400."""
        client, headers, _ = registered_client

        # Enable agent_tool_creation (which enables both propose_tool and fetch_docs)
        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"agent_tool_creation": True},
        )
        assert resp.status_code == 200

        resp = await client.post(
            "/api/docs/fetch",
            headers=headers,
            json={"url": "https://evil.com/docs/api"},
        )

        assert resp.status_code == 400
        assert "not in the documentation allowlist" in resp.json()["detail"]

    async def test_fetch_raw_githubusercontent_allowed(self, registered_client, mock_letta_client):
        """raw.githubusercontent.com is now allowed — raw README and source files from GitHub."""
        client, headers, _ = registered_client

        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"agent_tool_creation": True},
        )
        assert resp.status_code == 200

        mock_resp = _mock_httpx_response(
            text="def example(): pass",
            content_type="text/plain",
        )
        mock_client = _mock_async_client([mock_resp])

        with (
            patch("app.docs.routes.validate_docs_url", return_value=(True, "", "1.2.3.4")),
            patch("app.docs.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            resp = await client.post(
                "/api/docs/fetch",
                headers=headers,
                json={"url": "https://raw.githubusercontent.com/org/repo/main/README.md"},
            )

        assert resp.status_code == 200

    async def test_fetch_redirect_to_disallowed_domain_rejected(self, registered_client, mock_letta_client):
        """Redirects to disallowed domains are rejected mid-chain."""
        client, headers, _ = registered_client

        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"agent_tool_creation": True},
        )
        assert resp.status_code == 200

        # First response: redirect from allowed domain to evil.com
        redirect_resp = _mock_httpx_response(
            status_code=302,
            headers={"location": "https://evil.com/steal-data"},
        )
        mock_client = _mock_async_client([redirect_resp])

        with (
            patch(
                "app.docs.routes.validate_docs_url",
                side_effect=[
                    (True, "", "1.2.3.4"),  # Initial URL validation passes
                    (False, "Domain 'evil.com' is not in the documentation allowlist", ""),  # Redirect URL fails
                ],
            ),
            patch("app.docs.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            resp = await client.post(
                "/api/docs/fetch",
                headers=headers,
                json={"url": "https://falconpy.readthedocs.io/en/latest/Hosts.html"},
            )

        assert resp.status_code == 400
        assert "Redirect to disallowed URL" in resp.json()["detail"]

    async def test_fetch_oversized_response_returns_413(self, registered_client, mock_letta_client):
        """Responses exceeding MAX_DOCS_RESPONSE_SIZE return 413."""
        client, headers, _ = registered_client

        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"agent_tool_creation": True},
        )
        assert resp.status_code == 200

        # Create a response larger than 1MB
        large_text = "x" * (1_048_577)
        mock_resp = _mock_httpx_response(text=large_text, content_type="text/plain")
        mock_client = _mock_async_client([mock_resp])

        with (
            patch("app.docs.routes.validate_docs_url", return_value=(True, "", "1.2.3.4")),
            patch("app.docs.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            resp = await client.post(
                "/api/docs/fetch",
                headers=headers,
                json={"url": "https://falconpy.readthedocs.io/en/latest/Hosts.html"},
            )

        assert resp.status_code == 413
        assert "too large" in resp.json()["detail"].lower()

    async def test_fetch_html_converted_to_text(self, registered_client, mock_letta_client):
        """HTML responses are converted to plain text (tags stripped)."""
        client, headers, _ = registered_client

        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"agent_tool_creation": True},
        )
        assert resp.status_code == 200

        html = "<html><body><script>alert('xss')</script><p>API Method: query_devices(limit)</p></body></html>"
        mock_resp = _mock_httpx_response(text=html, content_type="text/html")
        mock_client = _mock_async_client([mock_resp])

        with (
            patch("app.docs.routes.validate_docs_url", return_value=(True, "", "1.2.3.4")),
            patch("app.docs.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            resp = await client.post(
                "/api/docs/fetch",
                headers=headers,
                json={"url": "https://falconpy.readthedocs.io/en/latest/Hosts.html"},
            )

        assert resp.status_code == 200
        content = resp.json()["content"]
        # Script content should be stripped
        assert "alert" not in content
        assert "xss" not in content
        # But the API method should be preserved
        assert "query_devices" in content

    async def test_fetch_json_response_not_converted(self, registered_client, mock_letta_client):
        """JSON responses (like PyPI API) are returned as-is, not HTML-converted."""
        client, headers, _ = registered_client

        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"agent_tool_creation": True},
        )
        assert resp.status_code == 200

        json_text = '{"info": {"name": "falconpy", "version": "1.0.0"}}'
        mock_resp = _mock_httpx_response(text=json_text, content_type="application/json")
        mock_client = _mock_async_client([mock_resp])

        with (
            patch("app.docs.routes.validate_docs_url", return_value=(True, "", "1.2.3.4")),
            patch("app.docs.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            resp = await client.post(
                "/api/docs/fetch",
                headers=headers,
                json={"url": "https://pypi.org/pypi/crowdstrike-falconpy/json", "package": "crowdstrike-falconpy"},
            )

        assert resp.status_code == 200
        content = resp.json()["content"]
        assert "falconpy" in content
        assert "1.0.0" in content

    async def test_fetch_timeout_returns_504(self, registered_client, mock_letta_client):
        """Timeout errors return 504 Gateway Timeout."""
        client, headers, _ = registered_client

        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"agent_tool_creation": True},
        )
        assert resp.status_code == 200

        import httpx

        mock_client = _mock_async_client([])
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with (
            patch("app.docs.routes.validate_docs_url", return_value=(True, "", "1.2.3.4")),
            patch("app.docs.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            resp = await client.post(
                "/api/docs/fetch",
                headers=headers,
                json={"url": "https://falconpy.readthedocs.io/en/latest/Hosts.html"},
            )

        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()

    async def test_fetch_package_returned_in_response(self, registered_client, mock_letta_client):
        """The package name is echoed back in the response."""
        client, headers, _ = registered_client

        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"agent_tool_creation": True},
        )
        assert resp.status_code == 200

        mock_resp = _mock_httpx_response(text="Some docs content", content_type="text/plain")
        mock_client = _mock_async_client([mock_resp])

        with (
            patch("app.docs.routes.validate_docs_url", return_value=(True, "", "1.2.3.4")),
            patch("app.docs.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            resp = await client.post(
                "/api/docs/fetch",
                headers=headers,
                json={"url": "https://falconpy.readthedocs.io/en/latest/Hosts.html", "package": "crowdstrike-falconpy"},
            )

        assert resp.status_code == 200
        assert resp.json()["package"] == "crowdstrike-falconpy"
