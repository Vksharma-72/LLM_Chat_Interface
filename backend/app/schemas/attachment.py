"""Attachment schemas (§15)."""

import uuid

from pydantic import BaseModel

from app.models import Attachment


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    kind: str
    url: str

    @classmethod
    def from_model(cls, attachment: Attachment) -> "AttachmentResponse":
        return cls(
            id=attachment.id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            size_bytes=attachment.size_bytes,
            kind=attachment.kind,
            url=f"/api/attachments/{attachment.id}/content",
        )
