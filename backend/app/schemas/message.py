"""Message schemas (§7): Message = {id, conversation_id, role, content, tokens,
metadata, created_at}. Built from ORM objects via from_model because the
column attribute is `metadata_` (SQLAlchemy reserves `metadata`)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models import Message


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    tokens: int | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime

    @classmethod
    def from_model(cls, message: Message) -> "MessageResponse":
        return cls(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            tokens=message.tokens,
            metadata=message.metadata_ or {},
            created_at=message.created_at,
        )
