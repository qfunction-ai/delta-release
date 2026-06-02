"""E2E tool proposal tests — propose, list, approve, reject flow."""

import time


def _unique_name(prefix: str) -> str:
    """Generate a unique tool name with timestamp suffix."""
    return f"{prefix}_{int(time.time() * 1000)}"


class TestToolProposals:
    """Tests for the tool proposal lifecycle."""

    def _ensure_toggle_on(self, e2e_client, e2e_token_manager):
        """Helper: enable the toggle before proposal tests."""
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": True,
            },
        )

    def _ensure_toggle_off(self, e2e_client, e2e_token_manager):
        """Helper: disable the toggle after proposal tests."""
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": False,
            },
        )

    def test_list_proposals_empty(self, e2e_client, e2e_token_manager):
        """GET /api/tools/proposals returns empty list when no proposals exist."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/tools/proposals")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_propose_and_list(self, e2e_client, e2e_token_manager):
        """Propose a tool, then verify it appears in the proposals list."""
        self._ensure_toggle_on(e2e_client, e2e_token_manager)
        try:
            # Propose
            name = _unique_name("e2e_list_proposal")
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/tools/propose",
                json={
                    "name": name,
                    "description": "Test proposal for listing",
                    "source_code": f"def {name}(q: str) -> str:\n    return q",
                    "json_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
                },
            )
            assert resp.status_code == 201
            proposal_id = resp.json()["id"]
            self.__class__.list_proposal_id = proposal_id

            # List proposals should include it
            resp = e2e_token_manager.request(e2e_client, "get", "/api/tools/proposals")
            assert resp.status_code == 200
            proposals = resp.json()
            assert any(p["id"] == proposal_id for p in proposals)
            assert any(p["proposed_by"] == "agent" for p in proposals)
        finally:
            self._ensure_toggle_off(e2e_client, e2e_token_manager)

    def test_propose_with_pip_requirements(self, e2e_client, e2e_token_manager):
        """Propose a tool with pip requirements specified."""
        self._ensure_toggle_on(e2e_client, e2e_token_manager)
        try:
            name = _unique_name("e2e_pip_proposal")
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/tools/propose",
                json={
                    "name": name,
                    "description": "Test proposal with pip requirements",
                    "source_code": f"def {name}(url: str) -> str:\n    import httpx\n    return url",
                    "json_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
                    "pip_requirements": ["httpx"],
                },
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["pip_requirements"] == ["httpx"]
            self.__class__.pip_proposal_id = data["id"]
        finally:
            self._ensure_toggle_off(e2e_client, e2e_token_manager)

    def test_propose_dangerous_code_blocked(self, e2e_client, e2e_token_manager):
        """Propose with dangerous code (os.system) is rejected by sanitizer."""
        self._ensure_toggle_on(e2e_client, e2e_token_manager)
        try:
            name = _unique_name("e2e_dangerous")
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/tools/propose",
                json={
                    "name": name,
                    "description": "Should be blocked by sanitizer",
                    "source_code": f"import os\ndef {name}(cmd: str) -> str:\n    os.system(cmd)\n    return cmd",
                    "json_schema": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]},
                },
            )
            # Should be 400 — sanitizer blocks os.system
            assert resp.status_code == 400
            assert "dangerous" in resp.json()["detail"].lower() or "os" in resp.json()["detail"].lower()
        finally:
            self._ensure_toggle_off(e2e_client, e2e_token_manager)

    def test_propose_safe_os_getenv_allowed(self, e2e_client, e2e_token_manager):
        """Propose with os.getenv is allowed — the canonical credential access pattern."""
        self._ensure_toggle_on(e2e_client, e2e_token_manager)
        try:
            name = _unique_name("e2e_safe_os")
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/tools/propose",
                json={
                    "name": name,
                    "description": "Uses os.getenv for credentials",
                    "source_code": f"import os\ndef {name}(key: str) -> str:\n    return os.getenv(key, '{{}}')",
                    "json_schema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
                },
            )
            assert resp.status_code == 201
            self.__class__.safe_os_proposal_id = resp.json()["id"]
        finally:
            self._ensure_toggle_off(e2e_client, e2e_token_manager)

    def test_approve_proposal(self, e2e_client, e2e_token_manager):
        """Approve a pending proposal — tool becomes active."""
        self._ensure_toggle_on(e2e_client, e2e_token_manager)
        try:
            # Create a proposal to approve
            name = _unique_name("e2e_approve")
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/tools/propose",
                json={
                    "name": name,
                    "description": "Test proposal for approval",
                    "source_code": f"def {name}(x: str) -> str:\n    return x",
                    "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            )
            assert resp.status_code == 201
            proposal_id = resp.json()["id"]

            # Approve it
            resp = e2e_token_manager.request(e2e_client, "post", f"/api/tools/proposals/{proposal_id}/approve")
            # Accept 200 (success) or 503 (Letta unavailable)
            assert resp.status_code in (200, 503), f"Approve failed: {resp.text}"
            if resp.status_code == 200:
                data = resp.json()
                assert data["status"] == "active"
                # Should now appear in the tools list
                resp = e2e_token_manager.request(e2e_client, "get", "/api/tools/")
                tools = resp.json()
                assert any(t["id"] == proposal_id for t in tools)
        finally:
            self._ensure_toggle_off(e2e_client, e2e_token_manager)

    def test_reject_proposal(self, e2e_client, e2e_token_manager):
        """Reject a pending proposal — tool is deleted."""
        self._ensure_toggle_on(e2e_client, e2e_token_manager)
        try:
            # Create a proposal to reject
            name = _unique_name("e2e_reject")
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/tools/propose",
                json={
                    "name": name,
                    "description": "Test proposal for rejection",
                    "source_code": f"def {name}(x: str) -> str:\n    return x",
                    "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            )
            assert resp.status_code == 201
            proposal_id = resp.json()["id"]

            # Reject it
            resp = e2e_token_manager.request(e2e_client, "post", f"/api/tools/proposals/{proposal_id}/reject")
            assert resp.status_code == 204

            # Should no longer appear in proposals
            resp = e2e_token_manager.request(e2e_client, "get", "/api/tools/proposals")
            proposals = resp.json()
            assert not any(p["id"] == proposal_id for p in proposals)
        finally:
            self._ensure_toggle_off(e2e_client, e2e_token_manager)

    def test_approve_non_pending_fails(self, e2e_client, e2e_token_manager):
        """Approving a non-pending tool returns 400."""
        # Use the existing e2e_tool_id (which is active, not pending)
        from .conftest import _TOOL_SCHEMA, _TOOL_SOURCE

        # Use a unique name for the active tool
        name = _unique_name("e2e_active_not_pending")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/",
            json={
                "name": name,
                "description": "Active tool — approve should fail",
                "source_code": _TOOL_SOURCE,
                "json_schema": _TOOL_SCHEMA,
            },
        )
        assert resp.status_code == 201
        tool_id = resp.json()["id"]

        # Try to approve (it's active, not pending)
        resp = e2e_token_manager.request(e2e_client, "post", f"/api/tools/proposals/{tool_id}/approve")
        assert resp.status_code == 400

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/tools/{tool_id}")

    def test_duplicate_name_proposal_fails(self, e2e_client, e2e_token_manager):
        """Proposing a tool with an existing name returns 409."""
        self._ensure_toggle_on(e2e_client, e2e_token_manager)
        try:
            # Create first proposal
            name = _unique_name("e2e_dup")
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/tools/propose",
                json={
                    "name": name,
                    "description": "First proposal",
                    "source_code": f"def {name}(x: str) -> str:\n    return x",
                    "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            )
            assert resp.status_code == 201

            # Try duplicate name
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/tools/propose",
                json={
                    "name": name,
                    "description": "Duplicate proposal",
                    "source_code": f"def {name}(x: str) -> str:\n    return x",
                    "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            )
            assert resp.status_code == 409
        finally:
            self._ensure_toggle_off(e2e_client, e2e_token_manager)
