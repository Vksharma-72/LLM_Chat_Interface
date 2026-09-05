"""Attachment binding in the chat pipeline + multimodal prompts + cleanup."""

import json

import respx
from app.db.session import get_sessionmaker
from app.models import Attachment
from app.services import attachments as attachment_service
from sqlalchemy import select


def png_bytes(color: str = "red", size: int = 8) -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buffer, format="PNG")
    return buffer.getvalue()



def _completion(content: str) -> dict:
    return {
        "model": "test-model",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }


async def _upload(client, headers, name: str, content: bytes, mime: str) -> str:
    response = await client.post(
        "/api/attachments", headers=headers, files={"file": (name, content, mime)}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_send_with_image_builds_vision_prompt(
    client, registered_user, auth_headers, llm_url
):
    attachment_id = await _upload(
        client, auth_headers, "cat.png", png_bytes("orange"), "image/png"
    )

    with respx.mock:
        route = respx.post(f"{llm_url}/chat/completions").respond(
            json=_completion("It is a red square.")
        )
        response = await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"content": "What is this?", "attachment_ids": [attachment_id]},
        )

    assert response.status_code == 200, response.text
    body = json.loads(route.calls.last.request.read())
    user_content = body["messages"][0]["content"]
    assert isinstance(user_content, list)  # multimodal parts
    assert user_content[0]["type"] == "text"
    assert "What is this?" in user_content[0]["text"]
    image_part = user_content[1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")

    # response carries the bound attachment
    data = response.json()
    assert data["user_message"]["attachments"][0]["id"] == attachment_id

    # attachment is now bound to the message
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                select(Attachment).where(Attachment.id == attachment_id)
            )
        ).scalar_one()
    assert str(row.message_id) == data["user_message"]["id"]
    assert str(row.conversation_id) == data["conversation"]["id"]


async def test_send_document_text_reaches_llm(client, registered_user, auth_headers, llm_url):
    attachment_id = await _upload(
        client,
        auth_headers,
        "notes.txt",
        b"The launch code is ALPHA-1234.",
        "text/plain",
    )

    with respx.mock:
        route = respx.post(f"{llm_url}/chat/completions").respond(
            json=_completion("noted")
        )
        response = await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"content": "summarize", "attachment_ids": [attachment_id]},
        )

    assert response.status_code == 200
    body = json.loads(route.calls.last.request.read())
    assert "ALPHA-1234" in body["messages"][0]["content"]
    assert "[Document: notes.txt]" in body["messages"][0]["content"]


async def test_send_captionless_image_auto_titles(client, registered_user, auth_headers, llm_url):
    attachment_id = await _upload(
        client, auth_headers, "sunset.png", png_bytes("orange"), "image/png"
    )

    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(json=_completion("pretty"))
        response = await client.post(
            "/api/chat/send", headers=auth_headers, json={"attachment_ids": [attachment_id]}
        )

    assert response.status_code == 200
    assert response.json()["conversation"]["title"] == "📷 sunset.png"


async def test_send_foreign_attachment_404(client, registered_user, auth_headers):
    other = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "username": "other", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    foreign_id = await _upload(
        client, other_headers, "theirs.png", png_bytes(), "image/png"
    )

    response = await client.post(
        "/api/chat/send",
        headers=auth_headers,
        json={"content": "steal it", "attachment_ids": [foreign_id]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_send_reuses_bound_attachment_404(client, registered_user, auth_headers, llm_url):
    attachment_id = await _upload(
        client, auth_headers, "cat.png", png_bytes(), "image/png"
    )
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(json=_completion("ok"))
        first = await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"content": "first", "attachment_ids": [attachment_id]},
        )
    assert first.status_code == 200

    # the same attachment cannot be bound twice
    response = await client.post(
        "/api/chat/send",
        headers=auth_headers,
        json={"content": "second", "attachment_ids": [attachment_id]},
    )
    assert response.status_code == 404


async def test_vision_disabled_falls_back_to_text_note(
    client, registered_user, auth_headers, llm_url, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "LLM_VISION_ENABLED", False)
    attachment_id = await _upload(
        client, auth_headers, "cat.png", png_bytes(), "image/png"
    )

    with respx.mock:
        route = respx.post(f"{llm_url}/chat/completions").respond(
            json=_completion("text only")
        )
        response = await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"content": "what is this", "attachment_ids": [attachment_id]},
        )

    assert response.status_code == 200
    body = json.loads(route.calls.last.request.read())
    content = body["messages"][0]["content"]
    assert isinstance(content, str)  # plain text, no parts
    assert "[User attached image: cat.png]" in content


async def test_stream_meta_includes_attachments(
    client, registered_user, auth_headers, llm_url, parse_sse
):
    attachment_id = await _upload(
        client, auth_headers, "cat.png", png_bytes(), "image/png"
    )

    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            content='data: {"model":"test-model","choices":[{"delta":{"content":"seen"}}]}\n\n'
            'data: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )
        async with client.stream(
            "POST",
            "/api/chat/stream",
            headers=auth_headers,
            json={"content": "look", "attachment_ids": [attachment_id]},
        ) as response:
            assert response.status_code == 200
            events = await parse_sse(response)

    meta = events[0][1]
    assert meta["user_message"]["attachments"][0]["id"] == attachment_id


async def test_regenerate_resends_image_parts(
    client, registered_user, auth_headers, llm_url, parse_sse
):
    attachment_id = await _upload(
        client, auth_headers, "cat.png", png_bytes(), "image/png"
    )
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(
            json=_completion("first look")
        )
        sent = await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"content": "look", "attachment_ids": [attachment_id]},
        )
    conversation_id = sent.json()["conversation"]["id"]

    with respx.mock:
        route = respx.post(f"{llm_url}/chat/completions").respond(
            content='data: {"model":"test-model","choices":[{"delta":{"content":"second look"}}]}\n\n'
            'data: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )
        async with client.stream(
            "POST",
            "/api/chat/stream",
            headers=auth_headers,
            json={"conversation_id": conversation_id, "regenerate": True},
        ) as response:
            assert response.status_code == 200
            events = await parse_sse(response)

    assert events[-1][0] == "done"
    body = json.loads(route.calls.last.request.read())
    user_content = body["messages"][0]["content"]
    assert isinstance(user_content, list)
    assert any(part["type"] == "image_url" for part in user_content)

    detail = await client.get(f"/api/conversations/{conversation_id}", headers=auth_headers)
    assert [m["role"] for m in detail.json()["messages"]] == ["user", "assistant"]


async def test_delete_conversation_cascades_attachment_rows(
    client, registered_user, auth_headers, llm_url
):
    attachment_id = await _upload(
        client, auth_headers, "cat.png", png_bytes(), "image/png"
    )
    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").respond(json=_completion("ok"))
        sent = await client.post(
            "/api/chat/send",
            headers=auth_headers,
            json={"content": "with file", "attachment_ids": [attachment_id]},
        )
    conversation_id = sent.json()["conversation"]["id"]

    deleted = await client.delete(
        f"/api/conversations/{conversation_id}", headers=auth_headers
    )
    assert deleted.status_code == 204

    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                select(Attachment).where(Attachment.id == attachment_id)
            )
        ).scalar_one_or_none()
    assert row is None  # FK cascade removed the attachment row

    # the content route no longer finds it
    response = await client.get(
        f"/api/attachments/{attachment_id}/content", headers=auth_headers
    )
    assert response.status_code == 404


async def test_orphan_cleanup_removes_old_unbound(client, registered_user):
    from datetime import UTC, datetime, timedelta

    # an unbound attachment row, backdated past the 24h cutoff
    async with get_sessionmaker()() as session:
        row = Attachment(
            user_id=registered_user["user"]["id"],
            filename="old.png",
            stored_filename="old.png",
            mime_type="image/png",
            size_bytes=10,
            kind="image",
            created_at=datetime.now(UTC) - timedelta(hours=48),
        )
        session.add(row)
        await session.flush()
        row_id = row.id
        await session.commit()

    from app.services.attachments import upload_root

    directory = upload_root() / registered_user["user"]["id"] / str(row_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "old.png").write_bytes(b"x")

    async with get_sessionmaker()() as session:
        removed = await attachment_service.cleanup_orphans(session)

    assert removed >= 1
    async with get_sessionmaker()() as session:
        existing = (
            await session.execute(
                select(Attachment).where(Attachment.id == row_id)
            )
        ).scalar_one_or_none()
    assert existing is None
    assert not directory.exists()
