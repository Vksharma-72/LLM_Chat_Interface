"""Attachment storage, validation, text extraction, and prompt building (§15).

Files live under {UPLOAD_DIR}/{user_id}/{attachment_id}/. Everything written to
disk uses server-generated names; client filenames are display-only. The LLM
prompt builder converts attachments into OpenAI-compatible message content:
images become base64 `image_url` parts (downscaled derivative, gated by
LLM_VISION_ENABLED), documents contribute extracted text, and everything else
becomes a textual note.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import filetype
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Attachment

IMAGE_MAX_DIMENSION = 1024
MODEL_DERIVATIVE_NAME = "model.jpg"
CHUNK_SIZE = 1024 * 1024

# Types we refuse outright (active content / executables).
BLOCKED_MIME_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "application/x-dosexec",
    "application/x-executable",
    "application/x-sharedlib",
    "application/x-msdownload",
    "application/x-msi",
    "application/java-archive",
    "application/x-sh",
    "application/x-csh",
}


class AttachmentTooLarge(Exception):
    """Upload exceeded UPLOAD_MAX_FILE_MB."""


class UnsupportedFileType(Exception):
    """MIME type is blocked or cannot be handled safely."""


def upload_root() -> Path:
    root = Path(get_settings().UPLOAD_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def attachment_dir(attachment: Attachment) -> Path:
    return upload_root() / str(attachment.user_id) / str(attachment.id)


def original_path(attachment: Attachment) -> Path:
    return attachment_dir(attachment) / attachment.stored_filename


def model_derivative_path(attachment: Attachment) -> Path | None:
    if not attachment.model_image_path:
        return None
    return upload_root() / attachment.model_image_path


def sanitize_filename(name: str | None) -> str:
    """Client filenames are display-only: strip control chars/newlines, cap length."""
    cleaned = re.sub(r"[\r\n\t\x00-\x1f]", " ", name or "file")
    cleaned = cleaned.strip() or "file"
    return cleaned[:255]


def resolve_mime(declared: str | None, header: bytes, filename: str) -> str:
    """Trust magic bytes for binaries, fall back to the declared type, then guess."""
    guessed = filetype.guess(header) if header else None
    mime = guessed.mime if guessed else (declared or "").split(";")[0].strip().lower()
    if not mime:
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if mime in BLOCKED_MIME_TYPES:
        raise UnsupportedFileType(f"Files of type {mime} are not allowed")
    return mime


def detect_kind(mime: str, filename: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith(
        (
            "application/pdf",
            "text/",
            "application/vnd.openxmlformats-officedocument",
        )
    ) or mime in ("application/json", "application/msword", "application/rtf"):
        return "document"
    if mimetypes.guess_type(filename)[0] == mime and mime in (
        "application/sql",
        "application/xml",
    ):
        return "document"
    return "other"


async def save_stream(
    upload_file, destination: Path, max_bytes: int
) -> int:
    """Stream an UploadFile to disk in chunks, enforcing the size cap."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with destination.open("wb") as out:
            while chunk := await upload_file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise AttachmentTooLarge(
                        f"File exceeds the {max_bytes // (1024 * 1024)} MB limit"
                    )
                out.write(chunk)
    except AttachmentTooLarge:
        destination.unlink(missing_ok=True)
        raise
    return size


def make_model_derivative(attachment: Attachment) -> str | None:
    """Downscaled JPEG for the vision prompt; original on disk stays untouched."""
    source = original_path(attachment)
    try:
        with Image.open(source) as image:
            rgb = image.convert("RGB")
            rgb.thumbnail((IMAGE_MAX_DIMENSION, IMAGE_MAX_DIMENSION))
            derivative = attachment_dir(attachment) / MODEL_DERIVATIVE_NAME
            rgb.save(derivative, format="JPEG", quality=85)
    except Exception:
        return None
    relative = str(derivative.relative_to(upload_root()))
    return relative


def extract_text(source: Path, mime: str, filename: str, max_chars: int) -> str | None:
    """One-time text extraction for documents; None when nothing extractable."""
    try:
        text: str | None = None
        if mime == "application/pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(source))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif filename.lower().endswith(".docx") or "wordprocessingml" in mime:
            from docx import Document as DocxDocument

            document = DocxDocument(str(source))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        elif mime.startswith("text/") or mime in ("application/json", "application/sql"):
            text = source.read_text(encoding="utf-8", errors="replace")
        if text is None:
            return None
        text = text.strip()
        return text[:max_chars] if text else None
    except Exception:
        return None


async def cleanup_orphans(db: AsyncSession, older_than_hours: int = 24) -> int:
    """Delete unbound attachment rows (and their files) older than the cutoff,
    plus any on-disk directories with no database row. Returns rows removed."""
    import shutil
    from datetime import UTC, datetime, timedelta
    from uuid import UUID

    from sqlalchemy import select

    cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
    result = await db.execute(
        select(Attachment).where(
            Attachment.message_id.is_(None), Attachment.created_at < cutoff
        )
    )
    stale = list(result.scalars().all())
    for attachment in stale:
        shutil.rmtree(attachment_dir(attachment), ignore_errors=True)
        await db.delete(attachment)

    # Disk directories with no surviving database row (e.g. failed uploads).
    known_ids: set[UUID] = set((await db.execute(select(Attachment.id))).scalars())
    removed = len(stale)
    for user_dir in upload_root().iterdir():
        if not user_dir.is_dir():
            continue
        try:
            UUID(user_dir.name)
        except ValueError:
            continue
        for item in user_dir.iterdir():
            if item.is_dir() and item.name not in known_ids:
                shutil.rmtree(item, ignore_errors=True)
                removed += 1
    await db.commit()
    return removed


def build_llm_messages(
    content: str | None,
    attachments: Sequence[Attachment],
    *,
    include_images: bool = True,
) -> list[dict[str, Any]]:
    """Build the OpenAI user-turn message list from text + attachments (§15).

    Images become base64 image_url parts (downscaled derivative) when vision is
    enabled; documents contribute extracted text; everything else becomes a
    textual note so the model at least knows the file exists.
    """
    settings = get_settings()
    include_images = include_images and settings.LLM_VISION_ENABLED

    text_bits: list[str] = []
    image_parts: list[dict[str, Any]] = []
    for attachment in attachments:
        size_mb = attachment.size_bytes / (1024 * 1024)
        if attachment.kind == "image":
            if not include_images:
                text_bits.append(f"[User attached image: {attachment.filename}]")
                continue
            path = model_derivative_path(attachment) or original_path(attachment)
            try:
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            except OSError:
                text_bits.append(f"[User attached image: {attachment.filename}]")
                continue
            # the derivative is always JPEG; originals keep their real MIME
            part_mime = (
                "image/jpeg" if path.name == MODEL_DERIVATIVE_NAME else attachment.mime_type
            )
            image_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{part_mime};base64,{encoded}"},
                }
            )
        elif attachment.kind == "document":
            if attachment.extracted_text:
                text_bits.append(
                    f"[Document: {attachment.filename}]\n{attachment.extracted_text}"
                )
            else:
                text_bits.append(f"[User attached document: {attachment.filename}]")
        else:
            text_bits.append(
                f"[User attached {attachment.kind}: {attachment.filename} ({size_mb:.1f} MB)]"
            )

    prompt = "\n\n".join(bit for bit in [content, *text_bits] if bit) or "(see attachments)"
    if image_parts:
        return [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}, *image_parts],
            }
        ]
    return [{"role": "user", "content": prompt}]
