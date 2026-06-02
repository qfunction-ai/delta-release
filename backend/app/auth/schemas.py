import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.schemas import BaseORMSchema


class UserRegister(BaseModel):
    username: str
    password: str
    setup_token: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Username must be 3-50 characters")
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseORMSchema):
    id: UUID
    username: str
    role: str = "user"
    must_change_password: bool = False
    created_at: datetime
