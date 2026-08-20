# Version Pin: LettaLocal for Delta

Reviewer: Delta agent
Date: 2026-08-20

## The problem

Both `delta` and `delta-release` use `image: ghcr.io/qfunction-ai/letta-local:latest`.
Epsilon already pins to `:0.16.22`.

The course has shipped. Students are actively using Delta. `:latest` means
any LettaLocal release — including a broken one — gets pulled on the next
`docker compose pull`. A bad release would break Delta for every student
who updates.

## The fix

Pin both repos to a specific version:

```yaml
image: ghcr.io/qfunction-ai/letta-local:0.16.23
```

## Why 0.16.23 is the right pin

1. **Streaming works** (v0.16.22 fixed the UnboundLocalError, v0.16.23
   doesn't regress it)
2. **Agent deletion works** (CASCADE fix — Delta's `raise_on_error=False`
   was masking silent failures, leaving orphaned agents in the Letta DB)
3. **Policy validation is clearer** (rule name in error messages —
   backward-compatible improvement)
4. **Image is self-contained** (Dockerfile fix — PYTHONPATH workaround
   becomes redundant but harmless)
5. **Smoke rig exists** (pre-tag gate for future releases — reduces the
   risk of future regressions)

## When to bump the pin

Bump the pin deliberately, not automatically. The process:

1. LettaLocal agent ships a new version (tagged, smoke-tested)
2. Delta agent reviews the changelog and runs the 5 regression tests
   (see `docs/letta-v01623-delta-impact.md`)
3. If all pass, bump the pin in `docker-compose.yml`
4. Document the pin version and what changed in the pin comment

## What to do right now

1. Pin `delta-release` to `:0.16.23` (this is what students get)
2. Pin `delta` to `:0.16.23` (development repo)
3. Update the pin comment to document what 0.16.23 includes
4. Test by pulling the pinned image and running the 5 regression tests

## Pin comment

```yaml
# Letta Local fork (ghcr.io/qfunction-ai/letta-local)
# Pinned to 0.16.23:
#   0.16.22: streaming UnboundLocalError fix (V3 stream _ah shadow)
#   0.16.23: reset-messages soft-delete, policy rule-name errors,
#            agent-delete CASCADE fix, Dockerfile self-contained install
image: ghcr.io/qfunction-ai/letta-local:0.16.23
```
