import hmac

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.security import decode_access_token
from app.config import get_settings
from app.constants import COOKIE_NAME
from app.database import get_agent_by_letta_id_or_404, get_db

_security = HTTPBearer(auto_error=False)

# Use the shared cookie name constant
_COOKIE_NAME = COOKIE_NAME


async def _extract_token(request: Request) -> str | None:
    """Extract JWT from Authorization header or httpOnly cookie.

    Authorization header takes precedence (for API clients and service-to-service).
    Cookie is the fallback for browser-based requests.
    """
    # Try Authorization header first
    credentials = await _security(request)
    if credentials and credentials.credentials:
        return credentials.credentials

    # Fall back to httpOnly cookie
    cookie_token = request.cookies.get(_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get the current authenticated user from the JWT token.

    Supports both Authorization header (Bearer token) and httpOnly cookie.
    """
    token = await _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Check token version — reject if token was issued before a logout
    token_ver = payload.get("ver", 1)
    if token_ver != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Invalidate tokens issued before the last password change
    if user.password_changed_at is not None:
        token_issued = payload.get("iat")
        if token_issued is not None:
            from datetime import datetime, timezone

            # iat may be int (epoch) or datetime
            if isinstance(token_issued, int):
                issued_at = datetime.fromtimestamp(token_issued, tz=timezone.utc)
            elif isinstance(token_issued, datetime):
                issued_at = token_issued if token_issued.tzinfo else token_issued.replace(tzinfo=timezone.utc)
            else:
                issued_at = None
            if issued_at is not None:
                changed_at = user.password_changed_at
                if changed_at.tzinfo is None:
                    changed_at = changed_at.replace(tzinfo=timezone.utc)
                # JWT iat is truncated to integer seconds, so compare at
                # second granularity to avoid false positives when the
                # token was issued in the same second as the password change.
                issued_at_seconds = int(issued_at.timestamp())
                changed_at_seconds = int(changed_at.timestamp())
                if issued_at_seconds < changed_at_seconds:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token invalidated by password change. Please log in again.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

    # Set user_id on request state for audit middleware
    request.state.user_id = user.id

    return user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get the current user and verify they have admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def verify_service_token(request: Request):
    """Dependency: validate X-Service-Token header for internal service calls.

    Used by eval container endpoints that need to authenticate without
    a user JWT. The service token is configured via DELTA_SERVICE_TOKEN.

    Sets request.state.auth_method = "service_token" so the audit middleware
    can distinguish service-to-service calls from user JWT calls.
    """
    settings = get_settings()
    token = settings.service_token
    if not token:
        raise HTTPException(status_code=403, detail="Service token not configured")
    request_token = request.headers.get("X-Service-Token", "")
    if not hmac.compare_digest(request_token, token):
        raise HTTPException(status_code=403, detail="Invalid or missing service token")
    request.state.auth_method = "service_token"


async def resolve_agent_user(
    request: Request,
    agent_id: str,
    db: AsyncSession,
) -> "Agent":
    """Resolve the agent from agent_id and set user_id on request state.

    Shared helper for service-to-service endpoints that need to identify
    the user who owns an agent (eval chat, tool proposals, settings updates).
    Sets request.state.user_id so the audit middleware can attribute the action.

    Callers must first verify the service token via Depends(verify_service_token).
    """
    agent = await get_agent_by_letta_id_or_404(db, agent_id)
    request.state.user_id = agent.user_id
    return agent
