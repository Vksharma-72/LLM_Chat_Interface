"""Upload endpoint: kinds, validation, caps, ownership, content serving."""

import io

from app.core.config import get_settings


def png_bytes(color: str = "red", size: int = 8) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buffer, format="PNG")
    return buffer.getvalue()



async def _upload(client, headers, name: str, content: bytes, mime: str):
    return await client.post(
        "/api/attachments", headers=headers, files={"file": (name, content, mime)}
    )


async def test_upload_image_roundtrip_and_content(client, registered_user, auth_headers):
    response = await _upload(client, auth_headers, "cat.png", png_bytes(), "image/png")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["kind"] == "image"
    assert data["filename"] == "cat.png"
    assert data["mime_type"] == "image/png"
    assert data["size_bytes"] > 0
    assert data["url"] == f"/api/attachments/{data['id']}/content"

    content = await client.get(data["url"], headers=auth_headers)
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/png")
    assert "inline" in content.headers["content-disposition"]
    assert content.content == png_bytes()


async def test_upload_document_extracts_text(client, registered_user, auth_headers):
    response = await _upload(
        client,
        auth_headers,
        "notes.txt",
        b"The launch code is ALPHA-1234.",
        "text/plain",
    )

    assert response.status_code == 201
    assert response.json()["kind"] == "document"

    metadata = await client.get(
        f"/api/attachments/{response.json()['id']}", headers=auth_headers
    )
    assert metadata.status_code == 200
    assert metadata.json()["kind"] == "document"


async def test_upload_docx_extracts_text(client, registered_user, auth_headers):
    from docx import Document

    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph("Quarterly revenue grew by eighteen percent.")
    document.save(buffer)
    buffer.seek(0)

    response = await _upload(
        client,
        auth_headers,
        "report.docx",
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert response.status_code == 201
    assert response.json()["kind"] == "document"


async def test_upload_rejects_html(client, registered_user, auth_headers):
    response = await _upload(
        client, auth_headers, "evil.html", b"<script>alert(1)</script>", "text/html"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_file_type"


async def test_upload_oversize_413(client, registered_user, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "UPLOAD_MAX_FILE_MB", 1)
    response = await _upload(
        client, auth_headers, "big.bin", b"\x00" * 1_500_000, "application/octet-stream"
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_video_upload_stored_without_extraction(client, registered_user, auth_headers):
    response = await _upload(
        client,
        auth_headers,
        "clip.mp4",
        b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64,
        "video/mp4",
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "video"

    content = await client.get(response.json()["url"], headers=auth_headers)
    assert content.status_code == 200
    assert "inline" in content.headers["content-disposition"]


async def test_attachment_content_and_metadata_cross_user_404(
    client, registered_user, auth_headers
):
    uploaded = await _upload(client, auth_headers, "cat.png", png_bytes(), "image/png")
    attachment_id = uploaded.json()["id"]

    other = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "username": "other", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    for path in (f"/api/attachments/{attachment_id}", f"/api/attachments/{attachment_id}/content"):
        response = await client.get(path, headers=other_headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


async def test_attachment_requires_authentication(client):
    response = await client.get("/api/attachments/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401

