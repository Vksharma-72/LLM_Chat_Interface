"""Chat request/response schemas (§7)."""

import uuid

from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse


class ChatSendRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    content: str = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    model: str | None = None

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        if len(value) > get_settings().MAX_MESSAGE_CHARS:
            raise ValueError(f"must be at most {get_settings().MAX_MESSAGE_CHARS} characters")
        return value


class ChatSendResponse(BaseModel):
    conversation: ConversationResponse
    user_message: MessageResponse
    assistant_message: MessageResponse


class ModelsResponse(BaseModel):
    models: list[str]


class StatusResponse(BaseModel):
    status: str  # "ok" | "unavailable"
    model: str | None = None
