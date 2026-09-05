"""Schema round-trips and constraint tests against the real Postgres test DB."""

from datetime import UTC, datetime

import pytest
from app.models import ApiUsage, Conversation, Message, User
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

# date.today() is local-time (ruff DTZ011) — derive the day from UTC like the app does.
TODAY = datetime.now(UTC).date()


async def test_user_round_trip_defaults(db_session):
    user = User(email="Alice@Example.com", username="alice", password_hash="hash")
    db_session.add(user)
    await db_session.flush()

    loaded = (await db_session.execute(select(User).where(User.id == user.id))).scalar_one()
    assert loaded.email == "alice@example.com"  # lowercased via @validates
    assert loaded.is_active is True
    assert loaded.is_admin is False
    assert loaded.last_login is None
    assert loaded.created_at.tzinfo is not None
    assert loaded.updated_at.tzinfo is not None
    # Both come from utcnow() during one flush — within a second of each other.
    assert abs((loaded.updated_at - loaded.created_at).total_seconds()) < 1


async def test_duplicate_email_rejected(db_session):
    db_session.add(User(email="dup@example.com", username="u1", password_hash="h"))
    await db_session.flush()
    db_session.add(User(email="dup@example.com", username="u2", password_hash="h"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_duplicate_username_rejected(db_session):
    db_session.add(User(email="a@example.com", username="same", password_hash="h"))
    await db_session.flush()
    db_session.add(User(email="b@example.com", username="same", password_hash="h"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_user_email_length_limit_320(db_session):
    user = User(email=f"{'x' * 308}@example.com", username="longmail", password_hash="h")
    db_session.add(user)
    await db_session.flush()
    assert len(user.email) == 320


async def test_conversation_title_default_and_fields(db_session, user_factory):
    user = await user_factory()
    conversation = Conversation(user_id=user.id)
    db_session.add(conversation)
    await db_session.flush()

    assert conversation.title == "New Conversation"
    assert conversation.is_pinned is False
    assert conversation.model is None
    assert conversation.created_at.tzinfo is not None


async def test_message_metadata_defaults_to_empty_object(db_session, conversation_factory):
    conversation = await conversation_factory()
    message = Message(conversation_id=conversation.id, role="user", content="hi")
    db_session.add(message)
    await db_session.flush()

    assert message.metadata_ == {}
    assert message.tokens is None
    assert message.created_at.tzinfo is not None


async def test_message_role_check_constraint(db_session, conversation_factory):
    conversation = await conversation_factory()
    db_session.add(
        Message(conversation_id=conversation.id, role="bogus", content="hi")
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_message_content_not_null(db_session, conversation_factory):
    conversation = await conversation_factory()
    db_session.add(Message(conversation_id=conversation.id, role="user", content=None))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_api_usage_unique_user_date(db_session, user_factory):
    user = await user_factory()
    db_session.add(ApiUsage(user_id=user.id, date=TODAY, total_tokens=1))
    await db_session.flush()
    db_session.add(ApiUsage(user_id=user.id, date=TODAY, total_tokens=2))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_updated_at_touched_on_modification(db_session, user_factory):
    user = await user_factory()
    original_updated_at = user.updated_at
    user.username = "renamed"
    await db_session.flush()

    assert user.updated_at > original_updated_at


async def test_table_counts_start_empty_per_test(db_session):
    for model in (User, Conversation, Message, ApiUsage):
        count = (
            await db_session.execute(select(func.count()).select_from(model))
        ).scalar_one()
        assert count == 0
