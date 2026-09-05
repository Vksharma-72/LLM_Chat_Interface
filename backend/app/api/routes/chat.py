"""Chat endpoints (§7): send (non-stream), stream (SSE), models, status.

The user message is persisted and committed BEFORE the LLM call so an LLM
failure still leaves the user message in place with no orphan assistant row.
"""

import json
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user, get_db
from app.api.errors import ApiError
from app.core.config import get_settings
from app.core.limiter import api_limit, chat_limit, limiter, user_key
from app.db.repositories import (
    ApiUsageRepository,
    ConversationRepository,
    MessageRepository,
)
from app.db.session import get_sessionmaker
from app.models import Conversation, Message, User
from app.schemas.chat import ChatSendRequest, ChatSendResponse, ModelsResponse, StatusResponse
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse
from app.services.llm import (
    LLMBadResponse,
    LLMRateLimited,
    LLMUnavailable,
    get_llm_service,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1024


def _auto_title(content: str) -> str:
    """First ~60 chars of the first user message (§7)."""
    flattened = " ".join(content.split())
    return flattened[:60] or "New Conversation"


async def _prepare_exchange(
    db: AsyncSession, user: User, body: ChatSendRequest
) -> tuple[Conversation, Message]:
    """Resolve/create the conversation, persist the user message, and commit.

    Committing here means a later LLM failure keeps the user message (§7).
    """
    conv_repo = ConversationRepository(db)
    if body.conversation_id is not None:
        conversation = await conv_repo.get(body.conversation_id)
        if conversation is None or conversation.user_id != user.id:
            raise ApiError(404, "not_found", "Conversation not found")
    else:
        conversation = await conv_repo.create(user.id, model=body.model)
        conversation.title = _auto_title(body.content)

    requested = {
        "temperature": body.temperature,
        "max_tokens": body.max_tokens,
        "model": body.model,
    }
    user_message = await MessageRepository(db).append(
        conversation.id,
        role="user",
        content=body.content,
        metadata={key: value for key, value in requested.items() if value is not None},
    )
    await db.commit()
    return conversation, user_message


def _llm_failure(exc: Exception) -> ApiError:
    if isinstance(exc, LLMRateLimited):
        return ApiError(
            429,
            "llm_rate_limited",
            "The model is busy. Try again soon.",
            headers={"Retry-After": "60"},
        )
    return ApiError(502, "llm_unavailable", "The model is currently unavailable")


async def _persist_assistant(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    content: str,
    usage: dict[str, int] | None,
    model: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str | None,
) -> Message:
    metadata: dict[str, object] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if system_prompt:
        metadata["system_prompt"] = system_prompt
    assistant = await MessageRepository(db).append(
        conversation_id,
        role="assistant",
        content=content,
        tokens=usage["completion_tokens"] if usage else None,
        metadata=metadata,
    )
    await ApiUsageRepository(db).increment(
        user_id, tokens=usage["completion_tokens"] if usage else 0, requests=1
    )
    return assistant


async def _prepare_regeneration(
    db: AsyncSession, user: User, body: ChatSendRequest
) -> tuple[Conversation, Message, str]:
    """Drop the trailing assistant reply; return the last user message as prompt."""
    assert body.conversation_id is not None  # guaranteed by ChatSendRequest
    conversation = await ConversationRepository(db).get(body.conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise ApiError(404, "not_found", "Conversation not found")

    repo = MessageRepository(db)
    messages = await repo.list_for_conversation(conversation.id)
    if messages and messages[-1].role == "assistant":
        await repo.delete_message(messages[-1])
        messages = messages[:-1]
        await db.commit()  # old reply is gone before the re-stream starts

    last_user = next((m for m in reversed(messages) if m.role == "user"), None)
    if last_user is None:
        raise ApiError(422, "validation_error", "Nothing to regenerate")
    return conversation, last_user, last_user.content


def _stream_error(code: str, message: str) -> dict[str, str]:
    return {"event": "error", "data": json.dumps({"error": {"code": code, "message": message}})}


@router.post("/send", response_model=ChatSendResponse)
@limiter.limit(chat_limit, key_func=user_key)
async def send_message(
    request: Request,
    body: ChatSendRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service=Depends(get_llm_service),
) -> ChatSendResponse:
    if body.regenerate:
        raise ApiError(
            422, "validation_error", "Regeneration is only supported on /api/chat/stream"
        )
    conversation, user_message = await _prepare_exchange(db, user, body)
    temperature = body.temperature if body.temperature is not None else DEFAULT_TEMPERATURE
    max_tokens = body.max_tokens if body.max_tokens is not None else DEFAULT_MAX_TOKENS

    try:
        result = await service.chat_completion(
            [{"role": "user", "content": body.content or ""}],
            model=body.model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=body.system_prompt,
        )
    except (LLMRateLimited, LLMBadResponse, LLMUnavailable) as exc:
        raise _llm_failure(exc) from exc

    assistant_message = await _persist_assistant(
        db,
        user.id,
        conversation.id,
        content=result["content"],
        usage=result["usage"],
        model=result["model"],
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=body.system_prompt,
    )
    await db.refresh(conversation)
    return ChatSendResponse(
        conversation=ConversationResponse.from_model(conversation),
        user_message=MessageResponse.from_model(user_message),
        assistant_message=MessageResponse.from_model(assistant_message),
    )


@router.post("/stream")
@limiter.limit(chat_limit, key_func=user_key)
async def stream_message(
    request: Request,
    body: ChatSendRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service=Depends(get_llm_service),
) -> EventSourceResponse:
    if body.regenerate:
        conversation, user_message, prompt_content = await _prepare_regeneration(db, user, body)
    else:
        conversation, user_message = await _prepare_exchange(db, user, body)
        prompt_content = body.content or ""
    temperature = body.temperature if body.temperature is not None else DEFAULT_TEMPERATURE
    max_tokens = body.max_tokens if body.max_tokens is not None else DEFAULT_MAX_TOKENS

    return EventSourceResponse(
        _chat_stream_events(
            service,
            user.id,
            conversation,
            user_message,
            prompt_content,
            body,
            temperature,
            max_tokens,
        )
    )


async def _chat_stream_events(
    service,
    user_id: uuid.UUID,
    conversation: Conversation,
    user_message: Message,
    prompt_content: str,
    body: ChatSendRequest,
    temperature: float,
    max_tokens: int,
):
    """SSE events: meta → delta* → done{assistant_message, usage} (§7).

    Runs on its own DB session because the request-scoped one may be closed
    by the time the response generator streams.
    """
    yield {
        "event": "meta",
        "data": json.dumps(
            {
                "conversation_id": str(conversation.id),
                "user_message": MessageResponse.from_model(user_message).model_dump(mode="json"),
            }
        ),
    }

    parts: list[str] = []
    usage: dict[str, int] | None = None
    model_used: str | None = body.model
    session = get_sessionmaker()()
    try:
        async for event in service.chat_completion_stream(
            [{"role": "user", "content": prompt_content}],
            model=body.model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=body.system_prompt,
        ):
            if event["type"] == "delta":
                parts.append(event["content"])
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": event["content"]}),
                }
            elif event["type"] == "usage":
                usage = event["usage"]
            elif event["type"] == "done":
                model_used = event.get("model") or model_used
                async with session.begin():
                    assistant = await _persist_assistant(
                        session,
                        user_id,
                        conversation.id,
                        content="".join(parts),
                        usage=usage,
                        model=model_used or "unknown",
                        temperature=temperature,
                        max_tokens=max_tokens,
                        system_prompt=body.system_prompt,
                    )
                yield {
                    "event": "done",
                    "data": json.dumps(
                        {
                            "assistant_message": MessageResponse.from_model(
                                assistant
                            ).model_dump(mode="json"),
                            "usage": usage,
                        }
                    ),
                }
            elif event["type"] == "error":
                yield _stream_error(event["error"]["code"], event["error"]["message"])
                return
    except LLMRateLimited as exc:
        yield _stream_error("llm_rate_limited", str(exc))
        return
    except (LLMBadResponse, LLMUnavailable) as exc:
        yield _stream_error("llm_unavailable", str(exc))
        return
    finally:
        await session.close()


@router.get("/models", response_model=ModelsResponse)
@limiter.limit(api_limit, key_func=user_key)
async def get_models(
    request: Request,
    user: User = Depends(get_current_user),
    service=Depends(get_llm_service),
) -> ModelsResponse:
    try:
        models = await service.list_models()
    except (LLMRateLimited, LLMBadResponse, LLMUnavailable) as exc:
        raise _llm_failure(exc) from exc
    return ModelsResponse(models=models)


@router.get("/status", response_model=StatusResponse)
@limiter.limit(api_limit, key_func=user_key)
async def get_status(
    request: Request,
    user: User = Depends(get_current_user),
    service=Depends(get_llm_service),
) -> StatusResponse:
    healthy = await service.health()
    model = get_settings().LLM_MODEL or None
    if healthy and not model:
        try:
            models = await service.list_models()
            model = models[0] if models else None
        except (LLMRateLimited, LLMBadResponse, LLMUnavailable):
            model = None
    return StatusResponse(status="ok" if healthy else "unavailable", model=model)
