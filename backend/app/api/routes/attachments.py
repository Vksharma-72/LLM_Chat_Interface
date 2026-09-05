"""Attachment endpoints (§15): multipart upload + owner-scoped file serving."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.errors import ApiError
from app.core.config import get_settings
from app.core.limiter import api_limit, limiter, user_key
from app.db.repositories import AttachmentRepository
from app.models import User
from app.schemas.attachment import AttachmentResponse
from app.services import attachments as attachment_service
from app.services.attachments import (
    AttachmentTooLarge,
    UnsupportedFileType,
    original_path,
    sanitize_filename,
)

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

INLINE_TYPES = ("image/", "video/", "audio/", "application/pdf")


async def _get_owned_attachment(attachment_id: uuid.UUID, user: User, db: AsyncSession):
    attachment = await AttachmentRepository(db).get_for_user(attachment_id, user.id)
    if attachment is None:
        raise ApiError(404, "not_found", "Attachment not found")
    return attachment


@router.post("", response_model=AttachmentResponse, status_code=201)
@limiter.limit(api_limit, key_func=user_key)
async def upload_attachment(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttachmentResponse:
    settings = get_settings()
    max_bytes = settings.UPLOAD_MAX_FILE_MB * 1024 * 1024

    declared_mime = file.content_type
    header = await file.read(2048)
    await file.seek(0)
    display_name = sanitize_filename(file.filename)

    try:
        mime = attachment_service.resolve_mime(declared_mime, header, display_name)
    except UnsupportedFileType as exc:
        raise ApiError(422, "unsupported_file_type", str(exc)) from exc
    kind = attachment_service.detect_kind(mime, display_name)

    attachment = await AttachmentRepository(db).create(
        user_id=user.id,
        filename=display_name,
        stored_filename="",
        mime_type=mime,
        size_bytes=0,
        kind=kind,
    )
    suffix = Path(display_name).suffix[:16].replace("/", "_").replace("\\", "_")
    attachment.stored_filename = f"{attachment.id}{suffix}"

    destination = attachment_service.attachment_dir(attachment) / attachment.stored_filename
    try:
        size = await attachment_service.save_stream(file, destination, max_bytes)
    except AttachmentTooLarge as exc:
        raise ApiError(
            413,
            "payload_too_large",
            f"File exceeds the {settings.UPLOAD_MAX_FILE_MB} MB upload limit",
        ) from exc
    attachment.size_bytes = size

    if kind == "image":
        attachment.model_image_path = attachment_service.make_model_derivative(attachment)
    if kind == "document":
        attachment.extracted_text = attachment_service.extract_text(
            destination, mime, display_name, settings.DOC_MAX_CHARS
        )

    return AttachmentResponse.from_model(attachment)


@router.get("/{attachment_id}", response_model=AttachmentResponse)
@limiter.limit(api_limit, key_func=user_key)
async def get_attachment_metadata(
    request: Request,
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttachmentResponse:
    attachment = await _get_owned_attachment(attachment_id, user, db)
    return AttachmentResponse.from_model(attachment)


@router.get("/{attachment_id}/content")
@limiter.limit(api_limit, key_func=user_key)
async def get_attachment_content(
    request: Request,
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    attachment = await _get_owned_attachment(attachment_id, user, db)
    path: Path = original_path(attachment)
    if not path.is_file():
        raise ApiError(404, "not_found", "Attachment file missing")

    disposition = (
        "inline" if attachment.mime_type.startswith(INLINE_TYPES) else "attachment"
    )
    return FileResponse(
        path,
        media_type=attachment.mime_type,
        headers={"Content-Disposition": f'{disposition}; filename="{attachment.filename}"'},
    )
