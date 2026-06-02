"""E2E input validation tests — sanitizer, path traversal, and input constraints.

Tests the defense-in-depth sanitizer on tool creation, the propose toggle
enforcement, path traversal protection on eval-from-file, and password
minimum length.
"""


class TestToolSanitizer:
    """Verify the AST sanitizer blocks dangerous code patterns."""

    def test_subprocess_import_rejected(self, e2e_client, e2e_token_manager):
        """Tool source with 'import subprocess' is rejected."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/",
            json={
                "name": "sanitizer_subprocess_test",
                "description": "Should be blocked",
                "source_code": "import subprocess\ndef run_cmd(cmd: str) -> str:\n    return cmd",
                "json_schema": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]},
            },
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "dangerous" in resp.json()["detail"].lower() or "subprocess" in resp.json()["detail"].lower()

    def test_eval_call_rejected(self, e2e_client, e2e_token_manager):
        """Tool source with eval() is rejected."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/",
            json={
                "name": "sanitizer_eval_test",
                "description": "Should be blocked",
                "source_code": "def run_eval(code: str) -> str:\n    return eval(code)",
                "json_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            },
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "dangerous" in resp.json()["detail"].lower() or "eval" in resp.json()["detail"].lower()

    def test_dunder_import_rejected(self, e2e_client, e2e_token_manager):
        """Tool source with __import__() is rejected."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/",
            json={
                "name": "sanitizer_import_test",
                "description": "Should be blocked",
                "source_code": "def load_mod(name: str) -> str:\n    return __import__(name)",
                "json_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            },
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "dangerous" in resp.json()["detail"].lower() or "import" in resp.json()["detail"].lower()

    def test_os_system_rejected(self, e2e_client, e2e_token_manager):
        """Tool source with os.system() is rejected."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/",
            json={
                "name": "sanitizer_os_system_test",
                "description": "Should be blocked",
                "source_code": "import os\ndef run_cmd(cmd: str) -> str:\n    os.system(cmd)\n    return cmd",
                "json_schema": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]},
            },
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"

    def test_os_getenv_allowed(self, e2e_client, e2e_token_manager):
        """Tool source with os.getenv() is allowed — the credential access pattern."""
        import time

        name = f"sanitizer_safe_os_{int(time.time() * 1000)}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/",
            json={
                "name": name,
                "description": "Should be allowed",
                "source_code": "import os\ndef get_cred(key: str) -> str:\n    return os.getenv(key, '')",
                "json_schema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
            },
        )
        # Should succeed (201) or conflict if name taken (409)
        assert resp.status_code in (201, 409), f"Expected 201/409, got {resp.status_code}: {resp.text}"


class TestProposeToggle:
    """Verify the agent_tool_creation toggle gates the propose endpoint."""

    def test_propose_blocked_when_toggle_off(self, e2e_client, e2e_token_manager):
        """POST /api/tools/propose returns 403 when toggle is off."""
        # Ensure toggle is off
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": False,
            },
        )

        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/propose",
            json={
                "name": "toggle_off_test",
                "description": "Should be blocked",
                "source_code": "def toggle_off_test(x: str) -> str: return x",
                "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            },
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"


class TestPathTraversal:
    """Verify path traversal protection on eval-from-file."""

    def test_eval_from_file_path_traversal(self, e2e_client, e2e_token_manager):
        """POST /api/evals/run-from-file with ../../etc/passwd returns 400."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/evals/run-from-file",
            json={
                "file_path": "../../etc/passwd",
            },
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "evals directory" in resp.json()["detail"].lower() or "path" in resp.json()["detail"].lower()


class TestPasswordValidation:
    """Verify password constraints on change-password."""

    def test_password_too_short_rejected(self, e2e_client, e2e_token_manager):
        """POST /api/auth/change-password with short password returns 422/400."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/auth/change-password",
            json={
                "current_password": e2e_token_manager._password,
                "new_password": "short",
            },
        )
        # Pydantic validation returns 422, custom validation returns 400
        assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}"
