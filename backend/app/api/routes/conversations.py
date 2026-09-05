"""Conversation CRUD endpoints (§7) — owner-scoped, foreign ids return 404."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.errors import ApiError
from app.core.limiter import api_limit, limiter, user_key
from app.db.repositories import ConversationRepository, MessageRepository
from app.models import User
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListItem,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdateRequest,
)
from app.schemas.message import MessageResponse

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


async def _get_owned_conversation(
    conversation_id: uuid.UUID, user: User, db: AsyncSession
):
    conversation = await ConversationRepository(db).get(conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise ApiError(404, "not_found", "Conversation not found")
    return conversation


@router.get("", response_model=ConversationListResponse)
@limiter.limit(api_limit, key_func=user_key)
async def list_conversations(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(max_length=200)] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    repo = ConversationRepository(db)
    items, total = await repo.list_for_user(user.id, limit=limit, offset=offset, q=q)
    counts = await repo.message_counts([conversation.id for conversation in items])
    return ConversationListResponse(
        items=[
            ConversationListItem.from_model(conversation, counts.get(conversation.id, 0))
            for conversation in items
        ],
        total=total,
    )


@router.post("", response_model=ConversationResponse, status_code=201)
@limiter.limit(api_limit, key_func=user_key)
async def create_conversation(
    request: Request,
    body: ConversationCreateRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    title = (body.title if body else None) or "New Conversation"
    conversation = await ConversationRepository(db).create(user.id, title=title)
    return ConversationResponse.from_model(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
@limiter.limit(api_limit, key_func=user_key)
async def get_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    conversation = await _get_owned_conversation(conversation_id, user, db)
    messages = await MessageRepository(db).list_for_conversation(conversation_id)
    return ConversationDetailResponse(
        conversation=ConversationResponse.from_model(conversation),
        messages=[MessageResponse.from_model(message) for message in messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
@limiter.limit(api_limit, key_func=user_key)
async def update_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    body: ConversationUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    conversation = await _get_owned_conversation(conversation_id, user, db)
    conversation = await ConversationRepository(db).update(
        conversation, title=body.title, is_pinned=body.is_pinned
    )
    return ConversationResponse.from_model(conversation)


@router.delete("/{conversation_id}", status_code=204)
@limiter.limit(api_limit, key_func=user_key)
async def delete_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    conversation = await _get_owned_conversation(conversation_id, user, db)
    await ConversationRepository(db).delete(conversation)
