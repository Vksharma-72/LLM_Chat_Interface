"""Redis-backed rate limiting (PROJECT_PLAN.md §7).

Login limiting is a fixed window counter (INCR + EXPIRE) keyed by
client IP + submitted identifier, capped at RATE_LIMIT_LOGIN_PER_15MIN.
Chat/API-per-user limits arrive with slowapi in Step 5.
"""

from fastapi import Request
from redis.asyncio import Redis

from app.api.errors import ApiError
from app.core.config import get_settings

LOGIN_WINDOW_SECONDS = 15 * 60


async def enforce_login_rate_limit(
    request: Request, redis: Redis, username_or_email: str
) -> None:
    """Count every attempt; block once the identifier exceeds the configured cap."""
    settings = get_settings()
    ip = request.client.host if request.client else "unknown"
    key = f"login_rl:{ip}:{username_or_email.strip().lower()}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, LOGIN_WINDOW_SECONDS)
    if count > settings.RATE_LIMIT_LOGIN_PER_15MIN:
        raise ApiError(
            429,
            "rate_limited",
            "Too many login attempts. Try again later.",
            headers={"Retry-After": str(LOGIN_WINDOW_SECONDS)},
        )
