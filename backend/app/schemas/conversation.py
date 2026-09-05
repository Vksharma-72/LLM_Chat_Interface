"""Conversation schemas (§7)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models import Conversation
from app.schemas.message import MessageResponse


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ConversationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    is_pinned: bool | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    is_pinned: bool
    model: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, conversation: Conversation) -> "ConversationResponse":
        return cls(
            id=conversation.id,
            title=conversation.title,
            is_pinned=conversation.is_pinned,
            model=conversation.model,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class ConversationListItem(ConversationResponse):
    message_count: int = 0

    @classmethod
    def from_model(
        cls, conversation: Conversation, message_count: int = 0
    ) -> "ConversationListItem":
        base = ConversationResponse.from_model(conversation)
        return cls(**base.model_dump(), message_count=message_count)


class ConversationListResponse(BaseModel):
    items: list[ConversationListItem]
    total: int


class ConversationDetailResponse(BaseModel):
    conversation: ConversationResponse
    messages: list[MessageResponse]
