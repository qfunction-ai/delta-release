import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.schemas import UserLogin, UserRegister, UserResponse
from app.auth.security import create_access_token, hash_password, verify_password
from app.config import get_settings
from app.constants import COOKIE_NAME
from app.database import get_db
from app.rate_limit import limiter

# Advisory lock ID for serializing registration attempts (prevents race condition)
_REGISTRATION_LOCK_ID = 20240422

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Cookie settings for JWT — derive max age from JWT expiry so they stay in sync
_COOKIE_NAME = COOKIE_NAME


def _get_cookie_max_age() -> int:
    """Derive cookie max age from JWT expiry setting (seconds)."""
    return get_settings().jwt_expire_minutes * 60


def _set_auth_cookie(response: Response, token: str) -> None:
    """Set the JWT as an httpOnly cookie for browser-based auth.

    httpOnly cookies are not accessible to JavaScript, which prevents
    token theft via XSS. The cookie is also set with SameSite=Strict
    to prevent CSRF attacks.
    """
    settings = get_settings()
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=_get_cookie_max_age(),
        httponly=True,
        samesite="strict",
        secure=not settings.dev_mode,  # Secure in production (HTTPS only)
        path="/",
    )


@router.get("/setup-status")
async def setup_status(db: AsyncSession = Depends(get_db)):
    """Check if initial setup is needed (no users exist yet)."""
    result = await db.execute(select(func.count()).select_from(User).limit(1))
    user_count = result.scalar()
    settings = get_settings()
    response = {"needs_setup": user_count == 0}
    # Only reveal setup token requirement when setup is actually needed.
    # Once users exist, this information is irrelevant and leaking it
    # tells an attacker whether the instance requires a token for registration.
    if user_count == 0:
        response["requires_setup_token"] = bool(settings.setup_token)
    return response


@router.post("/register")
@limiter.limit("3/minute", auth=True)
async def register(request: Request, response: Response, user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Create the initial admin account. Only available when no users exist."""
    # Acquire advisory lock to prevent race condition where two concurrent
    # requests both observe an empty users table before either inserts.
    # pg_advisory_xact_lock is released automatically at transaction end.
    await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _REGISTRATION_LOCK_ID})

    # Check if any users already exist
    result = await db.execute(select(User).limit(1))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration is not available. An account already exists.",
        )

    # Validate setup token if one is configured
    settings = get_settings()
    if settings.setup_token:
        if not user_data.setup_token or not hmac.compare_digest(user_data.setup_token, settings.setup_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing setup token",
            )

    # Check for duplicate username (safety net for race conditions)
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    # Create the user (first user gets admin role)
    user = User(
        username=user_data.username,
        password_hash=hash_password(user_data.password),
        role="admin",
        must_change_password=False,
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role, "ver": user.token_version})

    # Set httpOnly cookie for browser-based auth
    _set_auth_cookie(response, access_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
    }


@router.post("/login")
@limiter.limit("5/minute", auth=True)
async def login(request: Request, response: Response, user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login and get an access token."""
    result = await db.execute(select(User).where(User.username == user_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role, "ver": user.token_version})

    # Set httpOnly cookie for browser-based auth
    _set_auth_cookie(response, access_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
    }


@router.post("/change-password")
@limiter.limit("3/minute", auth=True)
async def change_password(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    current_password: str = Body(...),
    new_password: str = Body(...),
):
    """Change user password."""
    # Verify current password
    if not verify_password(current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )

    current_user.password_hash = hash_password(new_password)
    current_user.must_change_password = False
    current_user.password_changed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"message": "Password changed successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout — invalidate all active sessions and clear the auth cookie.

    Bumps token_version so the JWT is rejected server-side on future
    requests, even if an attacker captured it. This is the only secure
    logout — simply deleting the cookie leaves the JWT valid for up to
    24 hours.
    """
    current_user.token_version += 1
    await db.commit()
    settings = get_settings()
    response.delete_cookie(key=_COOKIE_NAME, path="/", secure=not settings.dev_mode, samesite="strict")
    return None
