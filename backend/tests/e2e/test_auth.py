"""E2E auth tests — login, password change, token invalidation.

test_change_password and test_logout invalidate the session
token. They call e2e_token_manager.get_fresh_token() at the end to
restore it for subsequent tests.
"""


class TestLogin:
    def test_login_returns_token(self, e2e_client, e2e_token):
        """Login with valid credentials returns an access token."""
        assert e2e_token is not None
        assert len(e2e_token) > 20

    def test_login_wrong_password(self, e2e_client):
        """Login with wrong password returns 401."""
        resp = e2e_client.post(
            "/api/auth/login",
            json={
                "username": "e2e_test_user",
                "password": "WrongPassword123!",
            },
        )
        assert resp.status_code == 401


class TestAuthEdgeCases:
    def test_unauthenticated_access(self, e2e_client):
        """Accessing a protected endpoint without a token returns 401 or 403.

        Uses a fresh client to avoid cookie leakage from the session-scoped
        e2e_client (which carries the auth cookie from login).
        """
        import httpx

        with httpx.Client(base_url=e2e_client.base_url, timeout=e2e_client.timeout) as fresh:
            resp = fresh.get("/api/agents/")
            assert resp.status_code in (401, 403)

    def test_logout_clears_cookie(self, e2e_client, e2e_token_manager):
        """POST /api/auth/logout clears the cookie and invalidates the JWT.

        Logout bumps token_version server-side, so the JWT is rejected
        on future requests even if an attacker captured it.
        """
        headers = e2e_token_manager.headers()

        # Logout
        resp = e2e_client.post("/api/auth/logout", headers=headers)
        if resp.status_code == 401:
            e2e_token_manager.get_fresh_token()
            headers = e2e_token_manager.headers()
            resp = e2e_client.post("/api/auth/logout", headers=headers)
        assert resp.status_code == 204, f"Logout failed: {resp.status_code} {resp.text}"

        # The response should clear the delta_token cookie
        # (Set-Cookie with empty value or Max-Age=0)
        set_cookie = resp.headers.get("set-cookie", "")
        assert "delta_token" in set_cookie, f"Cookie not cleared: {set_cookie}"

        # Token should now be invalid (server-side invalidation via token_version)
        resp = e2e_client.get("/api/auth/me", headers=headers)
        assert resp.status_code == 401

        # Restore the session token for subsequent tests
        e2e_token_manager.get_fresh_token()

    def test_change_password(self, e2e_client, e2e_token_manager):
        """Change password flow: change, login with new, change back."""
        headers = e2e_token_manager.headers()

        # Determine current credentials
        username = e2e_token_manager._username
        current_pass = e2e_token_manager._password
        new_pass = "E2eNewPass456!"

        # Change password
        resp = e2e_client.post(
            "/api/auth/change-password",
            headers=headers,
            json={
                "current_password": current_pass,
                "new_password": new_pass,
            },
        )
        if resp.status_code == 401:
            # Token stale — refresh and retry
            e2e_token_manager.get_fresh_token()
            headers = e2e_token_manager.headers()
            resp = e2e_client.post(
                "/api/auth/change-password",
                headers=headers,
                json={
                    "current_password": current_pass,
                    "new_password": new_pass,
                },
            )
        assert resp.status_code == 200, f"Change password failed: {resp.text}"

        # Login with new password
        resp = e2e_client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": new_pass,
            },
        )
        assert resp.status_code == 200
        new_token = resp.json()["access_token"]

        # Change back to original — the second change invalidates new_token,
        # so we must re-login afterward to get a fresh token.
        headers_new = {"Authorization": f"Bearer {new_token}"}
        resp = e2e_client.post(
            "/api/auth/change-password",
            headers=headers_new,
            json={
                "current_password": new_pass,
                "new_password": current_pass,
            },
        )
        # The second change-password may itself return 401 if the token was
        # invalidated by the first change (race with iat check). If so,
        # re-login with the new password and retry.
        if resp.status_code == 401:
            resp2 = e2e_client.post(
                "/api/auth/login",
                json={
                    "username": username,
                    "password": new_pass,
                },
            )
            if resp2.status_code == 200:
                fresh_token = resp2.json()["access_token"]
                headers_fresh = {"Authorization": f"Bearer {fresh_token}"}
                resp = e2e_client.post(
                    "/api/auth/change-password",
                    headers=headers_fresh,
                    json={
                        "current_password": new_pass,
                        "new_password": current_pass,
                    },
                )
        assert resp.status_code == 200, f"Change back failed: {resp.text}"

        # Restore the session token
        e2e_token_manager.get_fresh_token()
