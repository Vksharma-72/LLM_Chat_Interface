"""Mock OpenAI-compatible LLM server (PROJECT_PLAN.md §1, S4).

The stand-in for the real llama.cpp/Llama-GUI server during all dev/E2E work.
Implements GET /v1/models and POST /v1/chat/completions (streaming and
non-streaming) with env-tunable reply text, latency and chunk count
(MOCK_LLM_REPLY, MOCK_LLM_LATENCY_MS, MOCK_LLM_CHUNKS, MOCK_LLM_PORT).

Run: uv run python scripts/mock_llm_server.py   (listens on :8001 by default)
"""

import asyncio
import json
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import uvicorn
from app.core.config import get_settings
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

settings = get_settings()
app = FastAPI(title="Mock LLM", version="0.1.0")

MOCK_MODEL_ID = "ornithopter-35b"


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _message_text(message: dict) -> str:
    """Content may be a plain string or OpenAI multimodal parts."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    parts = []
    for part in content if isinstance(content, list) else []:
        if isinstance(part, dict) and part.get("type") == "text":
            parts.append(str(part.get("text", "")))
    return " ".join(parts)


def _has_image_part(message: dict) -> bool:
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(
        isinstance(part, dict) and part.get("type") == "image_url" for part in content
    )


def _usage(body: dict[str, Any], reply: str) -> dict[str, int]:
    prompt_tokens = sum(_estimate_tokens(message) for message in body.get("messages", []))
    completion_tokens = _estimate_tokens(reply)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [{"id": MOCK_MODEL_ID, "object": "model", "owned_by": "mock"}],
    }


def _chunk(model: str, piece: str, finish_reason: str | None) -> str:
    payload = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [
            {"index": 0, "delta": {"content": piece}, "finish_reason": finish_reason}
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_events(body: dict[str, Any]) -> AsyncIterator[str]:
    reply = settings.MOCK_LLM_REPLY
    model = body.get("model") or MOCK_MODEL_ID
    usage = _usage(body, reply)

    pieces = max(1, settings.MOCK_LLM_CHUNKS)
    size = max(1, len(reply) // pieces)
    for index in range(0, len(reply), size):
        yield _chunk(model, reply[index : index + size], None)
    yield _chunk(model, "", "stop")

    final = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [],
        "usage": usage,
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Any:
    body = await request.json()
    if settings.MOCK_LLM_LATENCY_MS > 0:
        await asyncio.sleep(settings.MOCK_LLM_LATENCY_MS / 1000)

    reply = settings.MOCK_LLM_REPLY
    if any(_has_image_part(message) for message in body.get("messages", [])):
        reply = settings.MOCK_VISION_REPLY
    model = body.get("model") or MOCK_MODEL_ID

    if body.get("stream"):
        return StreamingResponse(
            _stream_events(body), media_type="text/event-stream"
        )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }
        ],
        "usage": _usage(body, reply),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=settings.MOCK_LLM_PORT)
