"""Auth request/response schemas (PROJECT_PLAN.md §7).

Password fields are capped at 72 chars — bcrypt's input limit — so hashing is
never silently truncated. Email is validated with a pragmatic pattern; the
stored value is always lowercased.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    email: str = Field(max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("username", mode="before")
    @classmethod
    def _strip_username(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class LoginRequest(BaseModel):
    username_or_email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("username_or_email", mode="before")
    @classmethod
    def _strip_identifier(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    username: str
    is_admin: bool
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
