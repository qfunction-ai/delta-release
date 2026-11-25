# Enterprise upgrade-path lessons (2026-11-25)

Delta is fresh-install-only demo software until the enterprise effort starts. The upgrade
machinery built on 2026-11-25 was archived rather than shipped, because there is no install
base to upgrade. This file records what the work taught us, so a future enterprise upgrade
path doesn't relearn it the hard way. The full implementation (scoped-role migration,
two-step secret re-sync, superuser fallback, PG password sentinel) lives on the branch
**`archive/delta-upgrade-path`** (at `35f4137`).

**Postgres table ownership when the database user changes.** `ALTER DATABASE … OWNER` does
not transfer ownership of the tables inside the database, and `REASSIGN OWNED` cannot move
objects owned by the bootstrap superuser. A migration that changes the connecting user
(e.g. from `postgres` to a scoped role) needs explicit per-object `ALTER TABLE … OWNER TO`
statements, enumerated from the catalog. Budget for this; it is not a one-liner.

**Re-sending unchanged secrets does not re-encrypt them.** LettaLocal's agent-manager
encryption filter reuses the stored ciphertext when the submitted plaintext is unchanged —
and legacy plaintext rows carry their plaintext in the ciphertext column (the
`Secret.from_plaintext` fallback), so a "re-sync" that re-sends the same secrets is a no-op:
the rows stay plaintext forever. A real re-encryption must force it (we used a two-step
clear-then-rewrite per agent). LettaLocal fixed the root cause separately (E-1), but any
upgrade tooling should verify ciphertext prefixes actually changed, not trust the write.

**Restart safety: one-time setup jobs run on every `up`.** Docker Compose restarts exited
one-shot services on every `docker compose up`, including `pull && up`. Anything destructive
in a one-shot's command (`rm -f`, truncate) executes against live data on every restart. Our
init-volumes service once did `rm -f && touch` on the encryption key — every restart would
have minted a fresh key over existing encrypted secrets, which is total data loss. Init
containers must be idempotent AND non-destructive: create-only-if-missing, never delete or
truncate.

**Key loss: never mint a second key over encrypted data.** If a key file is missing but the
encrypted data exists, generating a new key makes every existing secret permanently
undecryptable — and the server then refuses to start on the garbage ciphertext, so the
failure is total, not partial. Use sentinel markers: a sentinel that says "a secret was
provisioned here" plus an empty secret file means restore-from-backup, never mint. Keep the
sentinel OFF the volume it protects (or mirror it to a second volume), so a partial volume
loss can't take both the key and the proof the key existed.

**The S-1 trap: markers must mean what they say.** Our PG password sentinel meant "a scoped
credential is in use" — but the wrapper touched it even on the fallback branch where the
superuser credential was still in use. On the upgrade path that bricked the second start:
first boot warns and writes the sentinel, any restart before migration reads it as "scoped
credential present" and fails on the empty scoped password. A marker must only be written in
the state it describes.

**Docker Desktop's file-sharing layer breaks volume assumptions.** Named-volume roots are
created `root:root` 755 regardless of the consuming image's user, so non-root writers fail
until a one-shot fixes ownership. Setgid bits on the volume root do not survive the mount
layer (files created by initdb scripts landed with the wrong group). And `cap_drop: ALL`
plus `CHOWN`/`FOWNER` is not enough for root on VirtioFS — it needs `DAC_OVERRIDE` just to
stat a fresh volume directory. Any volume-bootstrap design must be tested on the actual
Docker Desktop host, not just Linux CI; none of these were catchable by mocks.

**The pgvector image has no python3.** Initdb scripts that shell out to `python3` (we used
it for URL-encoding a password) fail on the `pgvector/pgvector:pg16` image. Use alphanumeric
secrets so no encoding step is needed, or use SQL/POSIX tools that exist in the image.

**Configuration vs. credentials: two different channels.** The fork has sandbox-level
environment variables (global, database-stored, included for every agent's tools) as well as
per-agent secrets. Non-secret configuration such as a base URL fits the sandbox-level
channel better than per-agent secrets; credentials stay in per-agent secrets. We shipped
the base URL through per-agent secrets (the delivery code already existed and the channel
was proven live) — for the enterprise version, consider moving configuration values to
sandbox environment variables so they don't ride the credential sync path.

**Where the code is.** `archive/delta-upgrade-path` on `qfunction-ai/delta` (commit
`35f4137`): `scripts/create_letta_role.sh`, `scripts/resync_agent_secrets.sh`, the
two-step re-sync in `backend/app/credentials/service.py`, the superuser fallback and PG
sentinel in the letta wrapper, and the migration/re-sync test assertions. The Phase 1
security fixes themselves (F1–F9) shipped on the main branch — only the upgrade path was
archived.
