"""Typed async repositories over the SQLAlchemy models (PROJECT_PLAN.md §4).

Repositories never commit — transaction boundaries belong to the caller
(`api.deps.get_db` from Step 3 in the app; the rollback fixtures in tests/db).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import ApiUsage, Conversation, Message, RefreshToken, User


def _utc_today() -> date:
    return datetime.now(UTC).date()


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        email: str,
        username: str,
        password_hash: str,
        is_admin: bool = False,
    ) -> User:
        user = User(
            email=email, username=username, password_hash=password_hash, is_admin=is_admin
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.strip().lower())
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def touch_last_login(self, user: User) -> None:
        user.last_login = utcnow()
        await self.session.flush()


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        title: str | None = None,
        model: str | None = None,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id, title=title or "New Conversation", model=model
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
    ) -> tuple[list[Conversation], int]:
        """A user's conversations, pinned first then updated_at desc (§7), with total.

        `q` case-insensitively filters over conversation titles AND message content.
        """
        base = select(Conversation).where(Conversation.user_id == user_id)
        if q:
            pattern = f"%{q}%"
            base = base.where(
                or_(
                    Conversation.title.ilike(pattern),
                    Conversation.id.in_(
                        select(Message.conversation_id).where(Message.content.ilike(pattern))
                    ),
                )
            )
        total = (
            await self.session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        result = await self.session.execute(
            base.order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def message_counts(
        self, conversation_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not conversation_ids:
            return {}
        rows = await self.session.execute(
            select(Message.conversation_id, func.count(Message.id))
            .where(Message.conversation_id.in_(conversation_ids))
            .group_by(Message.conversation_id)
        )
        return {conversation_id: count for conversation_id, count in rows.all()}

    async def update(
        self,
        conversation: Conversation,
        *,
        title: str | None = None,
        is_pinned: bool | None = None,
    ) -> Conversation:
        if title is not None:
            conversation.title = title
        if is_pinned is not None:
            conversation.is_pinned = is_pinned
        conversation.updated_at = utcnow()
        await self.session.flush()
        return conversation

    async def delete(self, conversation: Conversation) -> None:
        await self.session.delete(conversation)
        await self.session.flush()


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        conversation_id: uuid.UUID,
        *,
        role: str,
        content: str,
        tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tokens=tokens,
            metadata_=metadata if metadata is not None else {},
        )
        self.session.add(message)
        # A new message is a conversation modification → touch updated_at (§6).
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=utcnow())
        )
        await self.session.flush()
        return message

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        """Messages ordered by created_at ascending (§7)."""
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())

    async def delete_message(self, message: Message) -> None:
        await self.session.delete(message)
        await self.session.flush()


class ApiUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def increment(
        self,
        user_id: uuid.UUID,
        *,
        tokens: int = 0,
        requests: int = 1,
        day: date | None = None,
    ) -> ApiUsage:
        """Upsert one row per user/day, accumulating tokens and requests (§6)."""
        day = day or _utc_today()
        await self.session.execute(
            pg_insert(ApiUsage)
            .values(user_id=user_id, date=day, total_tokens=tokens, total_requests=requests)
            .on_conflict_do_update(
                index_elements=[ApiUsage.__table__.c.user_id, ApiUsage.__table__.c.date],
                set_={
                    "total_tokens": ApiUsage.__table__.c.total_tokens + tokens,
                    "total_requests": ApiUsage.__table__.c.total_requests + requests,
                    "updated_at": utcnow(),
                },
            )
        )
        # Re-select with populate_existing: RETURNING would hand back a stale
        # identity-mapped instance when the row already existed in this session.
        result = await self.session.execute(
            select(ApiUsage)
            .where(ApiUsage.user_id == user_id, ApiUsage.date == day)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def list_for_user_since(self, user_id: uuid.UUID, start: date) -> list[ApiUsage]:
        result = await self.session.execute(
            select(ApiUsage).where(ApiUsage.user_id == user_id, ApiUsage.date >= start)
        )
        return list(result.scalars().all())


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, user_id: uuid.UUID, *, jti: str, expires_at: datetime
    ) -> RefreshToken:
        token = RefreshToken(user_id=user_id, jti=jti, expires_at=expires_at)
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.jti == jti)
        )
        return result.scalar_one_or_none()

    async def revoke(self, jti: str) -> bool:
        """Mark the token revoked; returns False when the jti does not exist."""
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.jti == jti)
            .values(revoked=True)
            .returning(RefreshToken.id)
        )
        return result.scalar_one_or_none() is not None
