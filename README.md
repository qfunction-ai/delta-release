# Delta

Self-hosted cybersecurity workflow automation powered by Letta agents.

## Architecture

```
┌─────────────┐   ┌─────────────┐   ┌──────────────┐   ┌──────────┐
│  Frontend   │──▶│   Backend   │──▶│ Letta Local  │──▶│  Ollama  │
│  React:3000 │   │ FastAPI:8000│   │  fork:8283   │   │  :11434  │
└─────────────┘   └──────┬──────┘   └──────┬───────┘   └──────────┘
                         │                 │
           ┌─────────────┼─────────────┐   │
           │             │             │   │
    ┌──────▼──────┐ ┌────▼─────┐      │
    │  PostgreSQL │ │ Pip      │      │
    │   :5432     │ │ Sidecar  │      │
    └──────┬──────┘ │  :8001   │      │
           │        └──────────┘      │
    ┌──────▼──────┐                    │
    │    Redis    │                    │
    │    :6379    │                    │
    └─────────────┘                    │
                                       │
                    ┌──────────────────┘ (opt-in)
                    │
             ┌──────▼──────┐
             │    Eval     │
             │   Runner    │
             │   :8003     │
             └─────────────┘
```

| Service | Port | Role |
|---------|------|------|
| Frontend | 3000 | React + TypeScript (Vite) |
| Backend | 8000 | FastAPI, async SQLAlchemy, Alembic migrations |
| Letta Local | 8283 | Forked Letta server ([ghcr.io/qfunction-ai/letta-local](https://github.com/qfunction-ai/letta-local)) — agent execution, memory, tools, plus audit logging, tool call policies, canary checks, file persistence, and observability |
| PostgreSQL | 5432 | Primary database (Delta + Letta) + APScheduler job store, with pgvector |
| Redis | 6379 | Letta caching |
| Pip Sidecar | 8001 | Package management (shared volume) |
| Eval Runner | 8003 | Agent evaluation (giskard-checks) — **opt-in**, not started by default |
| Ollama | 11434 | Local LLM inference (on host) |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- [Ollama](https://ollama.ai) running on the host with at least one model pulled (e.g. `gemma4:latest`)
- At least 4GB RAM for the Docker stack

### 1. Start

```bash
docker compose up -d
docker compose ps  # wait for all services healthy
```

Secrets (JWT, encryption key, service token) are auto-generated on first run and persisted to a Docker volume. No `.env` configuration required for local use. Edit `.env` to override defaults.

### 2. Login

Open http://localhost:3000. The first account is automatically assigned the **admin** role. After that, the login form appears for all subsequent visits.

### Managing Your Data

| Command | Effect |
|---------|--------|
| `docker compose stop` | Stop containers, keep all data |
| `docker compose down` | Stop and remove containers, **keep all data** (volumes preserved) |
| `docker compose down -v` | Stop and remove containers, **DELETE ALL DATA** (volumes removed) |
| `docker compose pull` | Update container images |
| `docker compose up -d` | Start (or restart after pull) |

Your agents, conversations, credentials, and settings are stored in Docker volumes. `docker compose down` preserves them. `docker compose down -v` destroys them permanently.

## Core Concepts

### Agents

Letta agents with a cybersecurity persona. Each agent has a chosen LLM model, an embedding model for memory, four memory blocks (`persona`, `human`, `workflow_context`, `findings`), base tools for conversation search and memory management, and file persistence tools (`file_list`, `file_read`, `file_write`, `grep_files`) for writing and searching files in a per-agent workspace.

The Letta Local fork adds a security layer: tool call policies (allow/deny/approve per tool), canary tokens in memory blocks for exfiltration detection, audit logging of all security events, and tool call recording for observability. Agent policies are configurable per-agent from the UI via the Policy tab on the agent detail page.

### Tools

Python functions that agents call during execution. Tools are written with type-annotated signatures, auto-converted to JSON schema for Letta's tool system, and stored in Letta's tool registry with metadata tracked in Delta's database. Tools can be created manually, imported from GitHub, or [proposed by agents](#tool-proposals).

**Tool authoring rules:**
- Never put credentials, API keys, or connection parameters in tool function signatures. Read them from environment variables inside the function body. The generated schema should only expose domain parameters (the query to run), not plumbing (who authenticates, where to connect).
- Tools that return large data should write to the agent's staging directory (`LETTA_STAGING_DIR` env var) and return a compact summary with `file_path` and `hint` fields. The runtime promotes staged files to the agent's persistent workspace after validation (size limits, path safety). The agent can then search the full data using `grep_files` or `file_read`.

### Skills

Instruction documents (SKILL.md) that guide agent behavior. Skills are uploaded as `.zip` packages, imported from GitHub, or created manually. At workflow runtime, skill content is injected into the agent's archival memory and discovered via `archival_memory_search`.

### Workflows

The execution unit — a prompt template bound to an agent, with optional tools and skills:

- **Prompt template** — supports `{{variable}}` placeholders, validated against injection
- **Tool/skill attachment** — selected tools and skills are attached before execution
- **Include reasoning** — captures the model's chain-of-thought separately
- **Scheduling** — cron expressions for recurring execution (APScheduler with PostgreSQL job store)
- **Execution modes** — synchronous (`/run`) or streaming via Server-Sent Events (`/stream`)

### Tool Proposals

When the `agent_tool_creation` setting is enabled, agents can propose new tools at runtime. The agent calls `propose_tool` with a name, description, source code, and JSON schema. The proposal enters a pending state with dry-run results, requiring human review and approval before activation.

### Credentials

Encrypted storage for security platform API keys. Supported providers include Splunk, CrowdStrike, SentinelOne, Elastic, and custom endpoints. All credentials are encrypted at rest with Fernet symmetric encryption and delivered to agents via Letta secrets at runtime — scoped per user, never globally.

### Chat

Ad-hoc agent conversations at `/chat`. Select any agent, attach tools and skills, toggle reasoning. Real-time SSE streaming with character-by-character animation.

### Observability

Full-stack observability at `/observability`. Three views:

- **Traces** — OpenTelemetry trace waterfalls from the Letta Local fork, showing agent step durations, tool calls, and LLM inference latency
- **Security Events** — Real-time feed of audit events (tool denials, policy violations, canary detections, approval requests) from the Letta Local fork's `security_events` table
- **Logs** — Aggregated logs from all services with service and severity filters

### Export/Import

Migrate tools, skills, and workflows between Delta instances. Export produces a JSON file with all user-owned resources; import recreates them on the target instance, resolving tool name references to the target's tool IDs.

### Docs

SSRF-safe documentation proxy for agents. Agents can fetch documentation from URLs at runtime through the `/api/docs/fetch` endpoint, which validates URLs against private IP ranges, pins resolved addresses to prevent DNS rebinding, converts HTML to text, and truncates responses.

### Execution Feedback Loop

Agents learn from their own execution history without model fine-tuning. After each workflow run, a lesson is extracted from the output or error. Lessons fall into three categories: `strategy` (what worked), `recovery` (how to avoid failures), and `optimization` (efficiency tips). Lessons are injected into archival memory before subsequent runs, tagged `["lessons"]`, and scored by utility — scores below -3 trigger auto-deletion.

### Evals

Agent quality evaluation using deterministic and LLM-based checks. The eval runner is a separate FastAPI service (port 8003) running `giskard-checks`. It is **not started by default** — bring it up with:

```bash
docker compose -f docker-compose.yml -f docker-compose.eval.yml up -d
```

Deterministic check types include `StringMatching`, `RegexMatching`, `Equals`, `NotEquals`, and `FnCheck`. LLM-based types include `Conformity` and `LLMJudge` (requires Ollama). Evals are accessible via the API at `/api/evals`.

### Settings

User settings that gate agent capabilities. Controls `agent_tool_creation` (tool proposal toggle) and `web_search_enabled` (web search tool attachment). Admin page at `/settings` also provides package management (pip install/uninstall to shared volume) and credential management.

## API

The backend exposes a REST API at `http://localhost:8000/api/`. All endpoints require JWT authentication except auth routes.

| Resource | Prefix | Operations |
|----------|--------|------------|
| Auth | `/api/auth` | Setup status, register, login, change password, logout, logout-everywhere, me |
| Agents | `/api/agents` | CRUD, list models, list embedding models |
| Tools | `/api/tools` | CRUD, generate schema, import from GitHub, propose, approve/reject proposals |
| Skills | `/api/skills` | CRUD, upload zip, import from GitHub, get content |
| Workflows | `/api/workflows` | CRUD, run, stream, list runs, get run |
| Credentials | `/api/credentials` | CRUD, test connectivity, list providers/types |
| Chat | `/api/chat` | Send message (sync), send message (SSE stream) |
| Settings | `/api/settings` | Get/update user settings |
| Lessons | `/api/lessons` | List all, list by workflow, delete |
| Evals | `/api/evals` | Scenario CRUD, run scenario, run from file, run history |
| Export/Import | `/api/export-import` | Export tools/skills/workflows, import from JSON file |
| Docs | `/api/docs` | SSRF-safe documentation fetch for agents |
| Audit | `/api/audit-logs` | List, export CSV, stats |
| Dashboard | `/api/dashboard` | Overview (agents, stats, health, recent runs) |
| Logs | `/api/logs` | View logs from all services (admin only) |
| Observability | `/api/observability` | Traces, security events, service logs |

## Security

**Authentication & Authorization** — JWT with bcrypt password hashing, token revocation via `token_version` increment. First-user registration (no default credentials), optional `DELTA_SETUP_TOKEN` gate in production. Admin role system.

**Credential Protection** — Fernet-encrypted at rest with PBKDF2-HMAC-SHA256 key derivation (600k iterations). Delivered to agents via Letta secrets — no runtime decryption endpoint. Scoped per user, not globally.

**Input Protection** — AST-based tool source code sanitizer (blocks dangerous imports, `eval`/`exec`/`open`/`globals`/`locals` regardless of aliasing). SSRF protection on credential test and docs fetch URLs. Prompt template validation against injection. ZIP decompression bomb protection. Skill content size limits.

**Infrastructure** — CORS with configurable origins (wildcard blocked in production). Rate limiting with auth-critical limits never relaxed in dev mode. Timing-safe service token comparison. Error detail sanitization (internal paths and tracebacks stripped). Audit logging middleware on all API requests. All containers run as non-root; Letta Local runs as UID 1000 with `cap_drop: ALL` (zero Linux capabilities), `no-new-privileges`, and read-only rootfs. Eval runner excluded from default stack to eliminate standing RCE attack surface. Postgres and Letta ports bound to 127.0.0.1 only.

**Agent Security Layer (Letta Local fork)** — Tool call policies (per-agent allow/deny/approve, fail-closed on load failure). Canary tokens in memory blocks for exfiltration detection. Audit logging to append-only `security_events` table. Tool call recording in `tool_calls` table. File staging with validation before promotion to agent workspace. All three agent versions (V1, V2, V3) enforce the same security stack.

## Configuration

All variables use the `DELTA_` prefix. Docker Compose maps them from `.env`.

**Auto-generated on first run** (no `.env` editing required for local use):

| Variable | Description |
|----------|-------------|
| `DELTA_JWT_SECRET` | Token signing key — auto-generated, persisted to `/data/config/` |
| `DELTA_CREDENTIALS_ENCRYPTION_KEY` | Fernet key for credential encryption — auto-generated, persisted |
| `DELTA_SERVICE_TOKEN` | Service-to-service auth token — auto-generated, persisted |

**Production overrides:**

| Variable | Description |
|----------|-------------|
| `DELTA_SETUP_TOKEN` | Prevents unauthenticated admin creation — set in production |
| `DELTA_JWT_SECRET` | Set explicitly in production (auto-generated value is for local dev only) |

**Commonly changed:**

| Variable | Default | Description |
|----------|---------|-------------|
| `DELTA_DATABASE_URL` | `postgresql://delta:delta@postgres:5432/delta` | PostgreSQL connection |
| `DELTA_LETTA_BASE_URL` | `http://letta:8283` | Letta Local fork server address |
| `DELTA_DEV_MODE` | off | Enables insecure defaults and SQL echo logging |
| `DELTA_CORS_ORIGINS` | `http://localhost:3000,...` | Comma-separated allowed origins |
| `DELTA_MAX_STEPS` | 50 | Max tool-calling steps per execution |
| `DELTA_VERIFY_TLS` | true | TLS verification for outbound requests |
| `DELTA_RATE_LIMIT_DEFAULT` | `100/minute` | Default rate limit; set `1000/minute` for dev/CI |

**Eval** (opt-in — start with `docker compose -f docker-compose.yml -f docker-compose.eval.yml up -d`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DELTA_EVAL_URL` | `http://eval:8003` | Eval container URL |
| `DELTA_EVALS_DIR` | `/app/evals` | Base directory for eval scenario YAML files |
| `DELTA_EVAL_JUDGE_MODEL` | `ollama/gemma4:latest` | LLM judge model for Conformity/LLMJudge checks |
| `DELTA_EVAL_JUDGE_BASE_URL` | `http://host.docker.internal:11434/v1` | LLM judge API base URL |

**Optional integrations:**

| Variable | Description |
|----------|-------------|
| `EXA_API_KEY` | Exa API key for agent web search (enables `web_search` tool) |

## Database Migrations

Migrations are managed with Alembic and run automatically on backend startup. To create a new migration:

```bash
docker compose exec backend alembic revision --autogenerate -m "description"
```

## Reset

To wipe all data and start fresh:

```bash
docker compose down -v && docker compose up -d
```

This removes all volumes (databases, agent data, credentials) and recreates everything. See [Managing Your Data](#managing-your-data) for the difference between `down` and `down -v`.
