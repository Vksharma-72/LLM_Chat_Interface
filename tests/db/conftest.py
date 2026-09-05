"""Fixtures for the database-layer tests (PROJECT_PLAN.md §12).

The schema is created fresh once per pytest session against TEST_DATABASE_URL;
each test then runs inside an outer transaction that is rolled back afterwards,
so tests never see each other's rows regardless of commits inside repositories.
"""

import asyncio
import itertools
import os
from typing import Any

import app.models  # noqa: F401  — registers all models on Base.metadata
import pytest
from app.db.base import Base
from app.models import Conversation, User
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat_test",
)


@pytest.fixture(scope="session")
def database_url() -> str:
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def _fresh_schema(database_url: str):
    """Drop + recreate the full schema once per pytest session."""

    async def _create() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())


@pytest.fixture
async def db_session(database_url: str, _fresh_schema) -> AsyncSession:
    """A session over an outer transaction that is rolled back at test end.

    `join_transaction_mode="create_savepoint"` keeps the session's own
    begin/commit/rollback semantics inside the outer transaction.
    """
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            session = AsyncSession(
                bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            try:
                yield session
            finally:
                await session.close()
                await outer.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
def user_seq() -> itertools.count:
    return itertools.count()


@pytest.fixture
async def user_factory(db_session: AsyncSession, user_seq: itertools.count):
    """Create a persisted User with a unique email/username unless given."""

    async def _make(
        email: str | None = None, username: str | None = None, **kwargs: Any
    ) -> User:
        n = next(user_seq)
        user = User(
            email=email or f"user{n}@example.com",
            username=username or f"user{n}",
            password_hash="test-password-hash",
            **kwargs,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _make


@pytest.fixture
async def conversation_factory(db_session: AsyncSession, user_factory):
    """Create a persisted Conversation for `user` (or a fresh user)."""

    async def _make(user: User | None = None, **kwargs: Any) -> Conversation:
        owner = user or await user_factory()
        conversation = Conversation(user_id=owner.id, **kwargs)
        db_session.add(conversation)
        await db_session.flush()
        return conversation

    return _make
