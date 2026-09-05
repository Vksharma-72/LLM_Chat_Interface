"""Users request/response schemas (PROJECT_PLAN.md §7)."""

import datetime as dt

from pydantic import BaseModel, Field, field_validator


class UserUpdateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)

    @field_validator("username", mode="before")
    @classmethod
    def _strip_username(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class UsageDay(BaseModel):
    date: dt.date
    tokens: int
    requests: int


class UsageResponse(BaseModel):
    days: list[UsageDay]
