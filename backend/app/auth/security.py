from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt as pyjwt

from app.config import get_settings


def hash_password(password: str) -> str:
    """Hash a plain text password."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(data: dict[str, Any]) -> str:
    """Create a JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode.update({"iat": now, "exp": expire})
    # Ensure role is included in token payload
    if "role" not in to_encode:
        to_encode["role"] = "user"
    # Ensure token version is included for revocation support
    if "ver" not in to_encode:
        to_encode["ver"] = 1
    return pyjwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT access token."""
    settings = get_settings()
    try:
        return pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except pyjwt.PyJWTError:
        return None
