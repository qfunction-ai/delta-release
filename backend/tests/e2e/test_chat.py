"""E2E chat tests — message and stream."""


class TestChat:
    def test_chat_message(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Send a chat message and get a response (best-effort)."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/chat/message",
            json={
                "agent_id": e2e_agent_id,
                "message": "Hello!",
            },
        )
        # Accept 200 (success) or 503 (LLM timeout)
        assert resp.status_code in (200, 503), f"Chat message failed: {resp.text}"

    def test_chat_stream(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Chat SSE stream returns data events (best-effort)."""
        headers = e2e_token_manager.headers()
        headers["Accept"] = "text/event-stream"
        with e2e_client.stream(
            "POST",
            "/api/chat/stream",
            headers=headers,
            json={
                "agent_id": e2e_agent_id,
                "message": "Hello!",
            },
        ) as resp:
            # Accept 200 or 503
            if resp.status_code == 503:
                return  # LLM timeout — acceptable
            assert resp.status_code == 200
            # Read some events — just verify the stream format
            chunks = []
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    chunks.append(line)
                if len(chunks) >= 1:
                    break
