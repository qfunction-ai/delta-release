"""
Rate limiting configuration using slowapi.

Limits requests per user to prevent abuse. In dev mode, set
DELTA_RATE_LIMIT_DEFAULT to a high value (e.g., "1000/minute") to
effectively disable rate limiting for E2E tests and local development.
"""

import logging
import os

from fastapi import HTTPException, Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def get_user_identifier(request: Request) -> str:
    """Get identifier for rate limiting - user_id if authenticated, else IP.

    For proxied requests, uses the rightmost X-Forwarded-For IP (the one
    set by the most trusted proxy). For direct requests, uses the
    connection IP.
    """
    if hasattr(request.state, "user_id"):
        return f"user:{request.state.user_id}"

    # Try X-Forwarded-For header (set by reverse proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the rightmost IP — this is the one set by the most
        # trusted proxy in the chain. Leftmost IPs can be spoofed.
        client_ip = forwarded.split(",")[-1].strip()
        return f"ip:{client_ip}"

    return f"ip:{get_remote_address(request)}"


# In dev mode, use a very high limit so E2E tests and local development
# never hit rate limits. Production uses the standard 100/minute.
_default_limit = os.getenv("DELTA_RATE_LIMIT_DEFAULT", "100/minute")

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
