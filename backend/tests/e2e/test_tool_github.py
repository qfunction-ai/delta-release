"""E2E GitHub tool upload tests — tool.yaml parsing from GitHub repos."""


class TestToolGitHubUpload:
    """Tests for POST /api/tools/github endpoint."""

    def test_github_upload_invalid_url(self, e2e_client, e2e_token_manager):
        """POST /api/tools/github rejects non-GitHub URLs."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/github",
            json={
                "github_url": "https://gitlab.com/some/repo",
            },
        )
        assert resp.status_code == 422  # Validation error

    def test_github_upload_missing_url(self, e2e_client, e2e_token_manager):
        """POST /api/tools/github rejects empty request body."""
        resp = e2e_token_manager.request(e2e_client, "post", "/api/tools/github", json={})
        assert resp.status_code == 422

    def test_github_upload_nonexistent_repo(self, e2e_client, e2e_token_manager):
        """POST /api/tools/github returns error for non-existent GitHub repo."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/github",
            json={
                "github_url": "https://github.com/qfunction-ai/nonexistent-repo-xyz-123",
            },
        )
        # Accept 400 (no tool.yaml), 404 (repo not found), or 502 (fetch failed)
        assert resp.status_code in (400, 404, 502, 503), f"Unexpected: {resp.status_code} {resp.text[:200]}"
