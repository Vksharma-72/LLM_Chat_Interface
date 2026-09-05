"""Repository behavior tests (users, conversations, messages, usage, refresh tokens)."""

from datetime import UTC, date, datetime, timedelta

from app.db.base import utcnow
from app.db.repositories import (
    ApiUsageRepository,
    ConversationRepository,
    MessageRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.models import ApiUsage
from sqlalchemy import select

# --- users -------------------------------------------------------------------


async def test_user_repo_create_get_by_email_username(db_session):
    repo = UserRepository(db_session)
    created = await repo.create(
        email="Repo@Example.COM", username="repo", password_hash="h"
    )

    assert created.email == "repo@example.com"
    assert created.is_admin is False

    by_email = await repo.get_by_email("  repo@example.com ")
    assert by_email is not None and by_email.id == created.id
    by_username = await repo.get_by_username("repo")
    assert by_username is not None and by_username.id == created.id
    by_id = await repo.get_by_id(created.id)
    assert by_id is not None and by_id.id == created.id

    assert await repo.get_by_email("missing@example.com") is None
    assert await repo.get_by_username("missing") is None


async def test_user_repo_create_sets_admin_flag(db_session):
    repo = UserRepository(db_session)
    admin = await repo.create(
        email="admin@example.com", username="admin", password_hash="h", is_admin=True
    )
    assert admin.is_admin is True


# --- conversations -------------------------------------------------------------


async def test_conversation_repo_list_pinned_first_then_updated_at_desc(db_session, user_factory):
    repo = ConversationRepository(db_session)
    user = await user_factory()

    older = await repo.create(user.id)
    older.updated_at = utcnow() - timedelta(hours=2)
    newer = await repo.create(user.id)
    newer.updated_at = utcnow() - timedelta(hours=1)
    pinned = await repo.create(user.id)
    pinned.is_pinned = True
    pinned.updated_at = utcnow() - timedelta(hours=3)  # pinned wins even though oldest
    await db_session.flush()

    items, total = await repo.list_for_user(user.id)
    assert total == 3
    assert [c.id for c in items] == [pinned.id, newer.id, older.id]

    page1, total = await repo.list_for_user(user.id, limit=2, offset=0)
    assert [c.id for c in page1] == [pinned.id, newer.id]
    assert total == 3
    page2, _ = await repo.list_for_user(user.id, limit=2, offset=1)
    assert [c.id for c in page2] == [newer.id, older.id]


async def test_conversation_repo_list_is_per_user(db_session, user_factory):
    repo = ConversationRepository(db_session)
    mine = await user_factory()
    theirs = await user_factory()
    await repo.create(theirs.id)
    mine_conv = await repo.create(mine.id)

    items, total = await repo.list_for_user(mine.id)
    assert total == 1
    assert items[0].id == mine_conv.id


async def test_conversation_repo_update_and_delete(db_session, user_factory):
    repo = ConversationRepository(db_session)
    user = await user_factory()
    conversation = await repo.create(user.id)
    before = conversation.updated_at

    await repo.update(conversation, title="Renamed", is_pinned=True)
    assert conversation.title == "Renamed"
    assert conversation.is_pinned is True
    assert conversation.updated_at > before

    await repo.update(conversation, title=None, is_pinned=False)
    assert conversation.title == "Renamed"  # None = no change
    assert conversation.is_pinned is False

    await repo.delete(conversation)
    assert await repo.get(conversation.id) is None


# --- messages ------------------------------------------------------------------


async def test_message_repo_append_and_ordered_list(db_session, conversation_factory):
    repo = MessageRepository(db_session)
    conversation = await conversation_factory()

    first = await repo.append(conversation.id, role="user", content="first")
    second = await repo.append(
        conversation.id,
        role="assistant",
        content="second",
        tokens=42,
        metadata={"model": "ornithopter-35b"},
    )
    # Deterministic ordering: rewrite created_at explicitly, then list.
    first.created_at = utcnow() - timedelta(minutes=2)
    second.created_at = utcnow() - timedelta(minutes=1)
    await db_session.flush()

    messages = await repo.list_for_conversation(conversation.id)
    assert [m.id for m in messages] == [first.id, second.id]
    assert messages[1].tokens == 42
    assert messages[1].metadata_ == {"model": "ornithopter-35b"}

    other = await conversation_factory()
    await repo.append(other.id, role="user", content="other conversation")
    assert len(await repo.list_for_conversation(conversation.id)) == 2


async def test_message_repo_append_touches_conversation_updated_at(
    db_session, conversation_factory
):
    msg_repo = MessageRepository(db_session)
    conversation = await conversation_factory()
    before = conversation.updated_at

    await msg_repo.append(conversation.id, role="user", content="hi")
    await db_session.refresh(conversation)

    assert conversation.updated_at > before
    # ...but nothing else on the conversation row changed
    assert conversation.title == "New Conversation"


# --- api usage -----------------------------------------------------------------


async def test_usage_repo_increment_accumulates_per_day(db_session, user_factory):
    repo = ApiUsageRepository(db_session)
    user = await user_factory()
    day = date(2026, 9, 5)

    first = await repo.increment(user.id, tokens=100, requests=1, day=day)
    assert (first.total_tokens, first.total_requests) == (100, 1)

    second = await repo.increment(user.id, tokens=50, requests=2, day=day)
    assert (second.total_tokens, second.total_requests) == (150, 3)
    assert second.id == first.id  # same row upserted

    await repo.increment(user.id, tokens=10, requests=1, day=date(2026, 9, 6))
    rows = (await db_session.execute(select(ApiUsage))).scalars().all()
    assert len(rows) == 2


async def test_usage_repo_increment_defaults_to_utc_today(db_session, user_factory):
    repo = ApiUsageRepository(db_session)
    user = await user_factory()

    usage = await repo.increment(user.id, tokens=5)
    assert usage.date == datetime.now(UTC).date()
    assert (usage.total_tokens, usage.total_requests) == (5, 1)


# --- refresh tokens ------------------------------------------------------------


async def test_refresh_token_repo_create_get_revoke(db_session, user_factory):
    repo = RefreshTokenRepository(db_session)
    user = await user_factory()

    token = await repo.create(
        user.id, jti="jti-abc-123", expires_at=utcnow() + timedelta(days=7)
    )
    assert token.revoked is False

    fetched = await repo.get_by_jti("jti-abc-123")
    assert fetched is not None and fetched.id == token.id

    assert await repo.revoke("jti-abc-123") is True
    fetched = await repo.get_by_jti("jti-abc-123")
    assert fetched is not None and fetched.revoked is True

    assert await repo.get_by_jti("missing-jti") is None
    assert await repo.revoke("missing-jti") is False
