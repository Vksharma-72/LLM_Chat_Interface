"""FastAPI dependencies: db session, redis client, current user (§4)."""

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.core.config import get_settings
from app.db.repositories import UserRepository
from app.db.session import get_sessionmaker
from app.models import User
from app.services.security import TokenError, TokenExpiredError, decode_token, user_id_from_payload

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Request-scoped session: commit on success, roll back on any error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the Bearer access token to an active user; 401 otherwise (§7)."""
    if credentials is None:
        raise ApiError(401, "unauthorized", "Authentication required")
    try:
        payload = decode_token(credentials.credentials, "access")
        user_id = user_id_from_payload(payload)
    except TokenExpiredError as exc:
        raise ApiError(401, "token_expired", "Token has expired") from exc
    except TokenError as exc:
        raise ApiError(401, "invalid_token", "Invalid token") from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise ApiError(401, "invalid_token", "Invalid token")
    request.state.user_id = str(user.id)  # used by the rate-limiter key func
    return user
