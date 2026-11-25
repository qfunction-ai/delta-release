"""
Rate limiting configuration using slowapi.

Limits requests per user to prevent abuse. In dev mode, set
DELTA_RATE_LIMIT_DEFAULT to a high value (e.g., "1000/minute") to
effectively disable rate limiting for E2E tests and local development.
"""

import logging

from fastapi import HTTPException, Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings

logger = logging.getLogger(__name__)


def get_user_identifier(request: Request) -> str:
    """Get identifier for rate limiting - user_id if authenticated, else IP.

    X-Forwarded-For is deliberately NOT honored. No legitimate client of
    this deployment sends it: the browser calls the backend directly and
    nginx serves only static assets (no proxy_pass, no XFF directive), so
    the header is purely attacker-controlled — trusting it let anyone
    rotate rate-limit keys at will (code review D-6). Unauthenticated
    requests key on the connection IP.
    """
    if hasattr(request.state, "user_id"):
        return f"user:{request.state.user_id}"

    return f"ip:{get_remote_address(request)}"


# Default limit comes from Settings (env DELTA_RATE_LIMIT_DEFAULT). In dev
# mode, use a very high limit so E2E tests and local development never hit
# rate limits. Production uses the standard 100/minute.
_default_limit = get_settings().rate_limit_default

limiter = Limiter(
    key_func=get_user_identifier,
    default_limits=[_default_limit],
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded."""
    logger.warning("Rate limit exceeded for %s", get_user_identifier(request))
    raise HTTPException(
        status_code=429,
        detail="Rate limit exceeded. Please slow down.",
        headers={"Retry-After": "60"},
    )


def _is_rate_limiting_relaxed() -> bool:
    """Check if rate limiting is effectively disabled (dev/E2E mode)."""
    # If the default limit is set to 1000+/minute, per-route limits are
    # also relaxed to match. This avoids per-route limits (e.g., 5/min on
    # login) blocking E2E test suites.
    try:
        limit_val = int(_default_limit.split("/")[0])
        return limit_val >= 500
    except (ValueError, IndexError):
        return False


# Override limiter.limit to relax per-route limits when in dev mode.
# This ensures that @limiter.limit("5/minute") on propose, import,
# etc. doesn't block E2E test suites that make rapid sequential requests.
# However, auth-critical rate limits are NEVER relaxed — even in dev mode,
# brute-force protection on login/register/password-change must remain.
# Auth-critical endpoints opt in by passing auth=True: @limiter.limit("5/minute", auth=True)
_original_limit = limiter.limit


def _relaxed_limit(limit_value, **kwargs):
    """Rate limit decorator that respects the relaxed dev-mode default."""
    is_auth = kwargs.pop("auth", False)
    if _is_rate_limiting_relaxed() and not is_auth:
        # Use the high default limit instead of the per-route limit
        return _original_limit(_default_limit, **kwargs)
    return _original_limit(limit_value, **kwargs)


limiter.limit = _relaxed_limit
