"""Async engine + sessionmaker bound to DATABASE_URL (PROJECT_PLAN.md §4).

Both are cached singletons; `expire_on_commit=False` keeps attribute access
working after commit in async flows. Tests override `DATABASE_URL` via env
vars (root `tests/conftest.py`), so this engine points at `llmchat_test`
during test runs.
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().DATABASE_URL, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)
