"""Foreign-key ON DELETE CASCADE tests: user → children, conversation → messages."""

from datetime import UTC, datetime, timedelta

from app.db.base import utcnow
from app.models import ApiUsage, Conversation, Message, RefreshToken, User
from sqlalchemy import delete, func, select

# date.today() is local-time (ruff DTZ011) — derive the day from UTC like the app does.
TODAY = datetime.now(UTC).date()


async def _count(db_session, model) -> int:
    return (await db_session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_delete_user_cascades_all_children(db_session, user_factory, conversation_factory):
    user = await user_factory()
    conversation = await conversation_factory(user)
    db_session.add(Message(conversation_id=conversation.id, role="user", content="hi"))
    db_session.add(
        RefreshToken(user_id=user.id, jti="jti-cascade", expires_at=utcnow() + timedelta(days=1))
    )
    db_session.add(ApiUsage(user_id=user.id, date=TODAY, total_tokens=7, total_requests=2))
    await db_session.flush()

    assert await _count(db_session, Conversation) == 1
    assert await _count(db_session, Message) == 1
    assert await _count(db_session, RefreshToken) == 1
    assert await _count(db_session, ApiUsage) == 1

    await db_session.execute(delete(User).where(User.id == user.id))
    await db_session.flush()

    assert await _count(db_session, Conversation) == 0
    assert await _count(db_session, Message) == 0
    assert await _count(db_session, RefreshToken) == 0
    assert await _count(db_session, ApiUsage) == 0


async def test_delete_conversation_cascades_messages_only(db_session, user_factory, conversation_factory):
    user = await user_factory()
    conversation = await conversation_factory(user)
    db_session.add(Message(conversation_id=conversation.id, role="user", content="one"))
    db_session.add(Message(conversation_id=conversation.id, role="assistant", content="two"))
    await db_session.flush()

    await db_session.execute(delete(Conversation).where(Conversation.id == conversation.id))
    await db_session.flush()

    assert await _count(db_session, Message) == 0
    assert await _count(db_session, Conversation) == 0
    assert await _count(db_session, User) == 1  # owner survives


async def test_cascade_is_scoped_to_the_deleted_user(db_session, user_factory, conversation_factory):
    survivor = await user_factory()
    removed = await user_factory()
    await conversation_factory(survivor)
    doomed = await conversation_factory(removed)

    await db_session.execute(delete(User).where(User.id == removed.id))
    await db_session.flush()

    remaining = (
        await db_session.execute(select(Conversation).where(Conversation.user_id == survivor.id))
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].id != doomed.id
