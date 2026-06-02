"""Tests for observability proxy routes."""

from unittest.mock import AsyncMock, patch

import pytest


class TestProxyGet:
    """Tests for _proxy_get helper."""

    @pytest.mark.asyncio
    async def test_proxy_get_success(self):
        """Successful Letta response is returned as JSON."""
        from unittest.mock import MagicMock

        from app.observability.routes import _proxy_get

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"runs": []}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.observability.routes.letta_base_url", return_value="http://letta:8283"),
            patch("app.observability.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await _proxy_get("/v1/runs/", {"limit": 10})

        assert result == {"runs": []}
        mock_client.get.assert_called_once_with("http://letta:8283/v1/runs/", params={"limit": 10})

    @pytest.mark.asyncio
    async def test_proxy_get_404(self):
        """404 from Letta raises HTTPException(404)."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from app.observability.routes import _proxy_get

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.observability.routes.letta_base_url", return_value="http://letta:8283"),
            patch("app.observability.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _proxy_get("/v1/runs/bad-id")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_proxy_get_500_returns_empty(self):
        """500 from Letta returns empty dict (metrics endpoint quirk)."""
        from unittest.mock import MagicMock

        from app.observability.routes import _proxy_get

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.observability.routes.letta_base_url", return_value="http://letta:8283"),
            patch("app.observability.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await _proxy_get("/v1/runs/run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/metrics")

        assert result == {}

    @pytest.mark.asyncio
    async def test_proxy_get_other_error(self):
        """Non-200/404/500 from Letta raises HTTPException with generic 502."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from app.observability.routes import _proxy_get

        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.text = "validation error"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.observability.routes.letta_base_url", return_value="http://letta:8283"),
            patch("app.observability.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _proxy_get("/v1/runs/")
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_proxy_get_connection_error(self):
        """Connection error to Letta raises 502."""
        import httpx
        from fastapi import HTTPException

        from app.observability.routes import _proxy_get

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.observability.routes.letta_base_url", return_value="http://letta:8283"),
            patch("app.observability.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _proxy_get("/v1/runs/")
            assert exc_info.value.status_code == 502
            assert "unavailable" in exc_info.value.detail.lower()


class TestOverviewRoute:
    """Tests for GET /api/observability/overview."""

    @pytest.mark.asyncio
    async def test_overview_no_params(self, registered_client):
        """Overview with no filters."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"total_runs": 5, "total_tool_calls": 20},
        ):
            resp = await client.get("/api/observability/overview", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["total_runs"] == 5

    @pytest.mark.asyncio
    async def test_overview_with_filters(self, registered_client):
        """Overview passes since/until/agent_id to Letta."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"total_runs": 1},
        ) as mock_proxy:
            resp = await client.get(
                "/api/observability/overview?since=2026-01-01T00:00:00Z&until=2026-01-31T00:00:00Z&agent_id=agent-1",
                headers=headers,
            )

        assert resp.status_code == 200
        call_args = mock_proxy.call_args
        assert call_args[0][0] == "/v1/observability/overview"
        params = call_args[0][1]
        assert params["since"] == "2026-01-01T00:00:00Z"
        assert params["until"] == "2026-01-31T00:00:00Z"
        assert params["agent_id"] == "agent-1"


class TestRunsRoutes:
    """Tests for GET /api/observability/runs."""

    @pytest.mark.asyncio
    async def test_list_runs_defaults(self, registered_client):
        """List runs with default params."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get("/api/observability/runs", headers=headers)

        assert resp.status_code == 200
        params = mock_proxy.call_args[0][1]
        assert params["limit"] == 100
        assert params["order"] == "desc"

    @pytest.mark.asyncio
    async def test_list_runs_with_filters(self, registered_client):
        """List runs passes all filters to Letta."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get(
                "/api/observability/runs?agent_id=a1&statuses=completed&limit=50&before=cursor1",
                headers=headers,
            )

        assert resp.status_code == 200
        params = mock_proxy.call_args[0][1]
        assert params["agent_id"] == "a1"
        assert params["statuses"] == "completed"
        assert params["limit"] == 50
        assert params["before"] == "cursor1"

    @pytest.mark.asyncio
    async def test_get_single_run(self, registered_client):
        """Get a single run by ID."""
        client, headers, _ = registered_client
        run_id = "run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"id": run_id, "status": "completed"},
        ) as mock_proxy:
            resp = await client.get(f"/api/observability/runs/{run_id}", headers=headers)

        assert resp.status_code == 200
        assert mock_proxy.call_args[0][0] == f"/v1/runs/{run_id}"

    @pytest.mark.asyncio
    async def test_list_run_steps(self, registered_client):
        """List steps for a run."""
        client, headers, _ = registered_client
        run_id = "run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get(f"/api/observability/runs/{run_id}/steps", headers=headers)

        assert resp.status_code == 200
        assert mock_proxy.call_args[0][0] == f"/v1/runs/{run_id}/steps"

    @pytest.mark.asyncio
    async def test_get_run_metrics(self, registered_client):
        """Get metrics for a run."""
        client, headers, _ = registered_client
        run_id = "run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"prompt_tokens": 100},
        ) as mock_proxy:
            resp = await client.get(f"/api/observability/runs/{run_id}/metrics", headers=headers)

        assert resp.status_code == 200
        assert mock_proxy.call_args[0][0] == f"/v1/runs/{run_id}/metrics"

    @pytest.mark.asyncio
    async def test_get_run_usage(self, registered_client):
        """Get token usage for a run."""
        client, headers, _ = registered_client
        run_id = "run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"total_tokens": 500},
        ) as mock_proxy:
            resp = await client.get(f"/api/observability/runs/{run_id}/usage", headers=headers)

        assert resp.status_code == 200
        assert mock_proxy.call_args[0][0] == f"/v1/runs/{run_id}/usage"


class TestStepMetricsRoute:
    """Tests for GET /api/observability/steps/{step_id}/metrics."""

    @pytest.mark.asyncio
    async def test_get_step_metrics(self, registered_client):
        """Get metrics for a step."""
        client, headers, _ = registered_client
        step_id = "step-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"duration_ns": 12345},
        ) as mock_proxy:
            resp = await client.get(f"/api/observability/steps/{step_id}/metrics", headers=headers)

        assert resp.status_code == 200
        assert mock_proxy.call_args[0][0] == f"/v1/steps/{step_id}/metrics"


class TestToolCallsRoute:
    """Tests for GET /api/observability/tool-calls."""

    @pytest.mark.asyncio
    async def test_list_tool_calls_defaults(self, registered_client):
        """List tool calls with default params."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get("/api/observability/tool-calls", headers=headers)

        assert resp.status_code == 200
        params = mock_proxy.call_args[0][1]
        assert params["limit"] == 100

    @pytest.mark.asyncio
    async def test_list_tool_calls_with_filters(self, registered_client):
        """List tool calls passes all filters to Letta."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get(
                "/api/observability/tool-calls?agent_id=a1&tool_name=send_message&success=true&since=2026-01-01",
                headers=headers,
            )

        assert resp.status_code == 200
        params = mock_proxy.call_args[0][1]
        assert params["agent_id"] == "a1"
        assert params["tool_name"] == "send_message"
        assert params["success"] == "true"
        assert params["since"] == "2026-01-01"

    @pytest.mark.asyncio
    async def test_list_tool_calls_success_false(self, registered_client):
        """success=false is lowercased for Letta API."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get(
                "/api/observability/tool-calls?success=false",
                headers=headers,
            )

        assert resp.status_code == 200
        params = mock_proxy.call_args[0][1]
        assert params["success"] == "false"


class TestSecurityEventsRoute:
    """Tests for GET /api/observability/security-events."""

    @pytest.mark.asyncio
    async def test_security_events_default_since(self, registered_client):
        """Without since parameter, defaults to 7 days ago."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get("/api/observability/security-events", headers=headers)

        assert resp.status_code == 200
        params = mock_proxy.call_args[0][1]
        # since should be set to ~7 days ago
        assert "since" in params
        assert params["since"] is not None
        # Verify it's an ISO datetime string (not empty)
        assert len(params["since"]) > 10

    @pytest.mark.asyncio
    async def test_security_events_explicit_since(self, registered_client):
        """Explicit since parameter overrides the default."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get(
                "/api/observability/security-events?since=2026-01-01T00:00:00Z",
                headers=headers,
            )

        assert resp.status_code == 200
        params = mock_proxy.call_args[0][1]
        assert params["since"] == "2026-01-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_security_events_with_filters(self, registered_client):
        """agent_id and event_type filters are passed through."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get(
                "/api/observability/security-events?agent_id=a1&event_type=tool_denied&since=2026-01-01",
                headers=headers,
            )

        assert resp.status_code == 200
        params = mock_proxy.call_args[0][1]
        assert params["agent_id"] == "a1"
        assert params["event_type"] == "tool_denied"
        assert params["since"] == "2026-01-01"

    @pytest.mark.asyncio
    async def test_security_events_proxies_to_correct_path(self, registered_client):
        """Security events endpoint proxies to /v1/security/events."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get("/api/observability/security-events", headers=headers)

        assert resp.status_code == 200
        assert mock_proxy.call_args[0][0] == "/v1/security/events"

    @pytest.mark.asyncio
    async def test_security_events_limit_param(self, registered_client):
        """limit parameter is passed through."""
        client, headers, _ = registered_client
        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value={"items": []},
        ) as mock_proxy:
            resp = await client.get(
                "/api/observability/security-events?limit=50",
                headers=headers,
            )

        assert resp.status_code == 200
        params = mock_proxy.call_args[0][1]
        assert params["limit"] == 50


class TestRunTraceRoute:
    """Tests for GET /api/observability/runs/{run_id}/trace."""

    @pytest.mark.asyncio
    async def test_trace_with_spans(self, registered_client):
        """Returns transformed spans when Jaeger has trace data."""
        from unittest.mock import MagicMock

        client, headers, _ = registered_client

        # Mock _proxy_get to return steps with trace_id
        steps_data = [
            {"id": "step-1", "trace_id": "abc123def4567890"},
            {"id": "step-2", "trace_id": None},
        ]

        # Mock Jaeger response
        jaeger_resp = MagicMock()
        jaeger_resp.status_code = 200
        jaeger_resp.json.return_value = {
            "data": [
                {
                    "traceID": "abc123def4567890",
                    "spans": [
                        {
                            "spanID": "span-1",
                            "operationName": "agent_step",
                            "startTime": 1000000,
                            "duration": 500000,
                            "tags": [{"key": "step_id", "value": "step-1"}],
                            "references": [],
                        },
                        {
                            "spanID": "span-2",
                            "operationName": "OpenAIClient.request_async",
                            "startTime": 1100000,
                            "duration": 400000,
                            "tags": [],
                            "references": [{"refType": "CHILD_OF", "spanID": "span-1", "traceID": "abc123def4567890"}],
                        },
                    ],
                }
            ]
        }

        mock_jaeger_client = AsyncMock()
        mock_jaeger_client.get.return_value = jaeger_resp
        mock_jaeger_client.__aenter__ = AsyncMock(return_value=mock_jaeger_client)
        mock_jaeger_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.observability.routes._proxy_get",
                new_callable=AsyncMock,
                return_value=steps_data,
            ),
            patch("app.observability.routes.httpx.AsyncClient", return_value=mock_jaeger_client),
        ):
            resp = await client.get(
                "/api/observability/runs/run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/trace", headers=headers
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["trace_id"] == "abc123def4567890"
        assert len(body["spans"]) == 2

        # First span (root)
        root = body["spans"][0]
        assert root["operation_name"] == "agent_step"
        assert root["parent_span_id"] is None
        assert root["has_children"] is True
        assert root["tags"]["step_id"] == "step-1"

        # Second span (child)
        child = body["spans"][1]
        assert child["operation_name"] == "OpenAIClient.request_async"
        assert child["parent_span_id"] == "span-1"
        assert child["has_children"] is False

    @pytest.mark.asyncio
    async def test_trace_no_trace_id(self, registered_client):
        """Returns empty spans when steps have no trace_id."""
        client, headers, _ = registered_client

        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value=[{"id": "step-1", "trace_id": None}],
        ):
            resp = await client.get(
                "/api/observability/runs/run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/trace", headers=headers
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["trace_id"] is None
        assert body["spans"] == []

    @pytest.mark.asyncio
    async def test_trace_empty_steps(self, registered_client):
        """Returns empty spans when run has no steps."""
        client, headers, _ = registered_client

        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get(
                "/api/observability/runs/run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/trace", headers=headers
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["trace_id"] is None
        assert body["spans"] == []

    @pytest.mark.asyncio
    async def test_trace_jaeger_unavailable(self, registered_client):
        """Returns empty spans when Jaeger is unreachable."""
        import httpx

        client, headers, _ = registered_client

        mock_jaeger_client = AsyncMock()
        mock_jaeger_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_jaeger_client.__aenter__ = AsyncMock(return_value=mock_jaeger_client)
        mock_jaeger_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.observability.routes._proxy_get",
                new_callable=AsyncMock,
                return_value=[{"id": "step-1", "trace_id": "abc123def4567890"}],
            ),
            patch("app.observability.routes.httpx.AsyncClient", return_value=mock_jaeger_client),
        ):
            resp = await client.get(
                "/api/observability/runs/run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/trace", headers=headers
            )

        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_trace_jaeger_empty_response(self, registered_client):
        """Returns empty spans when Jaeger has no trace for the ID."""
        from unittest.mock import MagicMock

        client, headers, _ = registered_client

        jaeger_resp = MagicMock()
        jaeger_resp.status_code = 200
        jaeger_resp.json.return_value = {"data": []}

        mock_jaeger_client = AsyncMock()
        mock_jaeger_client.get.return_value = jaeger_resp
        mock_jaeger_client.__aenter__ = AsyncMock(return_value=mock_jaeger_client)
        mock_jaeger_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.observability.routes._proxy_get",
                new_callable=AsyncMock,
                return_value=[{"id": "step-1", "trace_id": "abc123def4567890"}],
            ),
            patch("app.observability.routes.httpx.AsyncClient", return_value=mock_jaeger_client),
        ):
            resp = await client.get(
                "/api/observability/runs/run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/trace", headers=headers
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["trace_id"] == "abc123def4567890"
        assert body["spans"] == []

    @pytest.mark.asyncio
    async def test_trace_spans_sorted_by_start_time(self, registered_client):
        """Spans are sorted by start_time_us."""
        from unittest.mock import MagicMock

        client, headers, _ = registered_client

        jaeger_resp = MagicMock()
        jaeger_resp.status_code = 200
        jaeger_resp.json.return_value = {
            "data": [
                {
                    "traceID": "abc123",
                    "spans": [
                        {
                            "spanID": "span-3",
                            "operationName": "third",
                            "startTime": 3000000,
                            "duration": 100000,
                            "tags": [],
                            "references": [],
                        },
                        {
                            "spanID": "span-1",
                            "operationName": "first",
                            "startTime": 1000000,
                            "duration": 100000,
                            "tags": [],
                            "references": [],
                        },
                        {
                            "spanID": "span-2",
                            "operationName": "second",
                            "startTime": 2000000,
                            "duration": 100000,
                            "tags": [],
                            "references": [],
                        },
                    ],
                }
            ]
        }

        mock_jaeger_client = AsyncMock()
        mock_jaeger_client.get.return_value = jaeger_resp
        mock_jaeger_client.__aenter__ = AsyncMock(return_value=mock_jaeger_client)
        mock_jaeger_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.observability.routes._proxy_get",
                new_callable=AsyncMock,
                return_value=[{"id": "step-1", "trace_id": "abc123def4567890"}],
            ),
            patch("app.observability.routes.httpx.AsyncClient", return_value=mock_jaeger_client),
        ):
            resp = await client.get(
                "/api/observability/runs/run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/trace", headers=headers
            )

        assert resp.status_code == 200
        body = resp.json()
        assert [s["operation_name"] for s in body["spans"]] == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_trace_rejects_non_hex_trace_id(self, registered_client):
        """Path-traversal trace_id is rejected and returns empty spans."""
        client, headers, _ = registered_client

        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value=[{"id": "step-1", "trace_id": "../services"}],
        ):
            resp = await client.get(
                "/api/observability/runs/run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/trace", headers=headers
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["spans"] == []

    @pytest.mark.asyncio
    async def test_trace_rejects_short_trace_id(self, registered_client):
        """trace_id shorter than 16 hex chars is rejected."""
        client, headers, _ = registered_client

        with patch(
            "app.observability.routes._proxy_get",
            new_callable=AsyncMock,
            return_value=[{"id": "step-1", "trace_id": "abc123"}],
        ):
            resp = await client.get(
                "/api/observability/runs/run-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/trace", headers=headers
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["spans"] == []


class TestProxyGetInfoDisclosure:
    """Tests for VULN-001: upstream error details must not leak to clients."""

    @pytest.mark.asyncio
    async def test_proxy_get_non200_hides_upstream_detail(self, registered_client):
        """Non-200/404/500 from Letta returns generic error, not resp.text."""
        from unittest.mock import MagicMock

        client, headers, _ = registered_client

        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.text = "Internal traceback: sqlalchemy.exc.IntegrityError..."

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.observability.routes.letta_base_url", return_value="http://letta:8283"),
            patch("app.observability.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            resp = await client.get("/api/observability/runs", headers=headers)

        assert resp.status_code == 502
        body = resp.json()
        # Must NOT contain the upstream error detail
        assert "traceback" not in body["detail"].lower()
        assert "sqlalchemy" not in body["detail"].lower()
        # Must be the generic message
        assert body["detail"] == "Upstream service error"
