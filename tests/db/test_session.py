"""Session/engine wiring: under pytest the app engine must point at the test DB."""

from app.db.session import get_engine, get_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession


def test_engine_points_at_test_database():
    # Root tests/conftest.py overrides DATABASE_URL to TEST_DATABASE_URL before
    # app imports, so the cached engine is bound to llmchat_test (§12).
    assert get_engine().url.database == "llmchat_test"


def test_sessionmaker_produces_async_sessions():
    session = get_sessionmaker()
    assert isinstance(session(), AsyncSession)
