"""Integration tests for lesson CRUD routes."""

import uuid

import pytest


@pytest.mark.asyncio
async def test_list_lessons_empty(registered_client):
    client, headers, _ = registered_client
    resp = await client.get("/api/lessons/", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["lessons"] == []


@pytest.mark.asyncio
async def test_list_workflow_lessons_empty(registered_client):
    client, headers, _ = registered_client
    # Use a random workflow ID — no lessons exist
    resp = await client.get(f"/api/lessons/{uuid.uuid4()}", headers=headers)
    # Should 404 since the workflow doesn't exist
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_lesson(registered_client):
    client, headers, _ = registered_client
    resp = await client.delete(f"/api/lessons/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_lesson_unauthorized(app_client):
    # No auth token
    resp = await app_client.delete(f"/api/lessons/{uuid.uuid4()}")
    assert resp.status_code in (401, 403)
