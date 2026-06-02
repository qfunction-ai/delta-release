"""E2E skill tests — create, get content, delete."""


class TestSkillCRUD:
    def test_create_skill(self, e2e_skill_id):
        """Skill was created by the fixture and has a valid ID."""
        assert e2e_skill_id is not None

    def test_get_skill_content(self, e2e_client, e2e_token_manager, e2e_skill_id):
        """Get skill content returns the SKILL.md text."""
        resp = e2e_token_manager.request(e2e_client, "get", f"/api/skills/{e2e_skill_id}/content")
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert "E2E Test Skill" in data["content"]

    def test_delete_skill(self, e2e_client, e2e_token_manager):
        """Create a skill, then delete it."""
        # Create a skill to delete (with YAML frontmatter)
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/skills/",
            json={
                "name": "e2e_delete_skill",
                "description": "A skill to be deleted",
                "content": "---\nname: e2e_delete_skill\n---\n\n# Delete Skill\n\nThis skill will be deleted.",
            },
        )
        assert resp.status_code == 201
        skill_id = resp.json()["id"]

        # Delete it
        resp = e2e_token_manager.request(e2e_client, "delete", f"/api/skills/{skill_id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = e2e_token_manager.request(e2e_client, "get", f"/api/skills/{skill_id}")
        assert resp.status_code == 404
