"""Chat request/response schemas (§7)."""

import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import get_settings
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse


class ChatSendRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    content: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    model: str | None = None
    system_prompt: str | None = Field(default=None, max_length=8000)
    regenerate: bool = False

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("must not be blank")
        max_chars = get_settings().MAX_MESSAGE_CHARS
        if len(value) > max_chars:
            raise ValueError(f"must be at most {max_chars} characters")
        return value

    @model_validator(mode="after")
    def _validate_combination(self) -> "ChatSendRequest":
        if self.regenerate:
            if self.conversation_id is None:
                raise ValueError("conversation_id is required when regenerating")
        elif self.content is None:
            raise ValueError("content is required")
        return self


class ChatSendResponse(BaseModel):
    conversation: ConversationResponse
    user_message: MessageResponse
    assistant_message: MessageResponse


class ModelsResponse(BaseModel):
    models: list[str]


class StatusResponse(BaseModel):
    status: str  # "ok" | "unavailable"
    model: str | None = None
