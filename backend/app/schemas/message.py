"""Message schemas (§7): Message = {id, conversation_id, role, content, tokens,
metadata, created_at, attachments}. Built from ORM objects via from_model
because the column attribute is `metadata_` (SQLAlchemy reserves `metadata`)
and the attachments relationship is only serialized when eagerly loaded."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models import Message
from app.schemas.attachment import AttachmentResponse


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    tokens: int | None = None
    metadata: dict[str, Any] = {}
    attachments: list[AttachmentResponse] = []
    created_at: datetime

    @classmethod
    def from_model(cls, message: Message) -> "MessageResponse":
        loaded = message.__dict__.get("attachments")  # only when eagerly loaded
        attachments = (
            [AttachmentResponse.from_model(a) for a in loaded] if loaded is not None else []
        )
        return cls(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            tokens=message.tokens,
            metadata=message.metadata_ or {},
            attachments=attachments,
            created_at=message.created_at,
        )
