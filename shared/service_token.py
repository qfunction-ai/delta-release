"""Shared service token loading and verification.

Used by eval and pip-sidecar services for internal authentication.
Each service loads its own kind of token — the eval container uses the
eval token (DELTA_EVAL_SERVICE_TOKEN), the pip-sidecar uses the sidecar
token (DELTA_SIDECAR_SERVICE_TOKEN). The backend generates both on first
run and writes them to the delta_secrets volume (/data/secrets), which
these services mount read-only.

The tool-callback token (DELTA_SERVICE_TOKEN) is a third, separate token
scoped to tool proposals and doc fetches. It is NOT loaded here — it is
delivered to agents via the agent secrets channel, and the backend
verifies it from its own settings object (auth/dependencies.py).

Token is cached for up to 5 minutes. If the token file is updated
(e.g., during a rotation), the next request after the cache expires
will pick up the new value. This avoids reading the file on every
request while still allowing rotation without a process restart.
"""

import hmac
import os
import time

from fastapi import HTTPException, Request

_TOKEN_KINDS = {
    "eval": ("DELTA_EVAL_SERVICE_TOKEN", "/data/secrets/eval_service_token"),
    "sidecar": ("DELTA_SIDECAR_SERVICE_TOKEN", "/data/secrets/sidecar_service_token"),
}

_SERVICE_TOKENS: dict[str, str | None] = {}
_SERVICE_TOKENS_LOADED_AT: dict[str, float] = {}
_TOKEN_TTL_SECONDS = 300  # 5 minutes


def _load_service_token(kind: str | None = None) -> str | None:
    """Load a service token from env var or the delta_secrets volume file.

    kind: "eval" or "sidecar". None (legacy) loads the tool-callback
    token from DELTA_SERVICE_TOKEN or /data/config/service_token — kept
    for backward compatibility with pre-F2 consumers.
    """
    if kind is None:
        token = os.environ.get("DELTA_SERVICE_TOKEN", "")
        if token:
            return token
        token_path = "/data/config/service_token"
    else:
        env_var, token_path = _TOKEN_KINDS[kind]
        token = os.environ.get(env_var, "")
        if token:
            return token
    try:
        with open(token_path, "r") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _get_service_token(kind: str | None = None) -> str | None:
    now = time.monotonic()
    cached = _SERVICE_TOKENS.get(kind)
    loaded_at = _SERVICE_TOKENS_LOADED_AT.get(kind, 0.0)
    if cached is None or (now - loaded_at) > _TOKEN_TTL_SECONDS:
        _SERVICE_TOKENS[kind] = _load_service_token(kind)
        _SERVICE_TOKENS_LOADED_AT[kind] = now
    return _SERVICE_TOKENS[kind]


def make_verify_service_token(kind: str):
    """Build a FastAPI dependency that validates X-Service-Token for a kind."""

    async def _verify(request: Request):
        token = _get_service_token(kind)
        if not token:
            raise HTTPException(status_code=403, detail="Service token not configured")
        request_token = request.headers.get("X-Service-Token", "")
        if not hmac.compare_digest(request_token, token):
            raise HTTPException(status_code=403, detail="Invalid or missing service token")

    return _verify


async def verify_service_token(request: Request):
    """Dependency: validate X-Service-Token header (legacy tool-callback token)."""
    token = _get_service_token()
    if not token:
        raise HTTPException(status_code=403, detail="Service token not configured")
    request_token = request.headers.get("X-Service-Token", "")
    if not hmac.compare_digest(request_token, token):
        raise HTTPException(status_code=403, detail="Invalid or missing service token")
