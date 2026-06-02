"""Shared service token loading and verification.

Used by eval and pip-sidecar services for internal authentication.
The backend has its own verify_service_token in auth/dependencies.py
which reads from the settings object instead.

Token is cached for up to 5 minutes. If the token file is updated
(e.g., during a rotation), the next request after the cache expires
will pick up the new value. This avoids reading the file on every
request while still allowing rotation without a process restart.
"""

import hmac
import os
import time

from fastapi import HTTPException, Request

_SERVICE_TOKEN: str | None = None
_SERVICE_TOKEN_LOADED_AT: float = 0.0
_TOKEN_TTL_SECONDS = 300  # 5 minutes


def _load_service_token() -> str | None:
    """Load service token from env var or shared volume file."""
    token = os.environ.get("DELTA_SERVICE_TOKEN", "")
    if token:
        return token
    token_path = "/data/config/service_token"
    try:
        with open(token_path, "r") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _get_service_token() -> str | None:
    global _SERVICE_TOKEN, _SERVICE_TOKEN_LOADED_AT
    now = time.monotonic()
    if _SERVICE_TOKEN is None or (now - _SERVICE_TOKEN_LOADED_AT) > _TOKEN_TTL_SECONDS:
        _SERVICE_TOKEN = _load_service_token()
        _SERVICE_TOKEN_LOADED_AT = now
    return _SERVICE_TOKEN


async def verify_service_token(request: Request):
    """Dependency: validate X-Service-Token header."""
    token = _get_service_token()
    if not token:
        raise HTTPException(status_code=403, detail="Service token not configured")
    request_token = request.headers.get("X-Service-Token", "")
    if not hmac.compare_digest(request_token, token):
        raise HTTPException(status_code=403, detail="Invalid or missing service token")
