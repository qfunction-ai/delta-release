# Delta Impact Analysis: LettaLocal v0.16.23 (commit c675964)

Reviewer: Delta agent
Date: 2026-08-20

## Summary: Positive — fixes silent agent deletion failures. No breaking changes.

## Commit c675964 changes and Delta impact

### 1. Dockerfile: `uv pip install --no-deps .`

Makes the GHCR image self-contained — the `letta` console script no longer
needs PYTHONPATH=/app to find the package.

Delta impact: **None.** Delta already sets `PYTHONPATH=/app:/extra-packages`
in docker-compose.yml (line 167 delta-release, line 168 delta). This becomes
redundant but harmless. No action needed — leave the PYTHONPATH as-is for
backwards compatibility with older images.

### 2. Alembic migration: CASCADE DELETE on security_events + tool_call_policies

Adds `ON DELETE CASCADE` to the FKs from `security_events.agent_id` and
`tool_call_policies.agent_id` to `agents.id`.

Delta impact: **Positive — fixes silent agent deletion failures.**

Delta deletes agents at `backend/app/agents/routes.py:247`:
```python
await call_letta(client.agents.delete, agent.letta_agent_id, raise_on_error=False)
```

The `raise_on_error=False` silently swallows Letta delete failures. On
v0.16.22, any Delta agent with a policy row or security event (which is
every agent that has a policy set or has executed tools) would fail the
Letta delete with a FK violation. Delta's DB row is deleted, but the Letta
agent is orphaned.

On v0.16.23 with CASCADE, the Letta delete succeeds. No more orphans.

Delta has the same problem as Epsilon, just masked differently:
- Epsilon: `delete_agent` raises on the 409, logs "Failed to delete agent"
- Delta: `delete_agent` uses `raise_on_error=False`, silently ignores the
  409, deletes the Delta DB row anyway, leaves the Letta agent orphaned

The CASCADE fix resolves both.

### 3. ORM cascade on agent.py

`cascade="all, delete-orphan"` + `passive_deletes=True` on the
agent→tool_call_policy relationship. This tells SQLAlchemy to let the
database handle the cascade (via the FK ON DELETE CASCADE) instead of
emulating it in Python.

Delta impact: **None.** Delta doesn't directly use the Letta ORM. Delta
uses the Letta REST API via the SDK. The ORM cascade is internal to the
Letta server.

### 4. Smoke test fixes (User-Agent header, OLLAMA_BASE_URL)

Smoke test only. No runtime impact on Delta.

## Migration safety

The migration `a9b8c7d6e5f4` revises `f3a4b5c6d7e8` (merge heads). Both
exist in the main checkout. The migration runs inside the Letta container
against the Letta DB on startup. Delta's alembic is separate (runs against
Delta's own DB). No conflict.

For existing Delta deployments with a populated Letta DB: the migration
will ALTER two FK constraints to add ON DELETE CASCADE. This is a metadata
operation (drop constraint + recreate with CASCADE) — no data changes.
Safe on a running Postgres. The constraint name assumptions
(`security_events_agent_id_fkey`, `tool_call_policies_agent_id_fkey`)
match Postgres default naming conventions.

## Testing Delta with v0.16.23

### What to test

1. **Streaming** (the rule after any LettaLocal version change):
   Send a chat message to a Delta agent. Verify token-by-token streaming,
   no `UnboundLocalError`, no "stopped with unknown error" in the SSE
   stream. v0.16.23 doesn't change streaming code from v0.16.22, so this
   should pass — but always verify.

2. **Agent deletion** (the main fix):
   Create an agent, set a policy on it (via the Policy tab), send a
   message (produces security events), then delete the agent. On v0.16.22,
   the Letta delete fails silently (orphaned agent). On v0.16.23, the
   delete should succeed — verify no orphaned agent in the Letta DB.

3. **Policy CRUD** (the rule-name error fix):
   PUT a policy with an invalid regex (e.g., `*confidential*` with
   `matches` operator). Verify the 400 response includes the rule name.
   PUT a policy with `contains` operator. Verify 200.

4. **Chat + tool calls** (regression):
   Send a message that triggers a tool call. Verify the tool executes,
   the response streams, and security events appear in the Logs page.

5. **Agent creation** (regression):
   Create a new agent. Verify file tools are attached, embedding model
   is set, model_settings include `provider_type: "ollama"`.

### How to test

```
# In delta-release directory:
docker compose pull letta-local  # pulls :latest (v0.16.23)
docker compose down -v
docker compose up -d --build
# Wait for health checks to pass
# Run through the 5 tests above
```

Or pin to `:0.16.23` explicitly before testing (recommended).

### What NOT to do

Do NOT run `docker compose down -v` on a Delta deployment with data you
want to preserve. The `-v` flag wipes volumes, including the Letta DB
and Postgres. For production Delta deployments (student machines), use
`docker compose down && docker compose up -d --build` (no `-v`) to
preserve data. The migration runs automatically on startup.
