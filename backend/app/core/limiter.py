"""slowapi rate limiter backed by Redis (§7): chat 20/min per user,
all other /api 120/hour per user. Keyed by the authenticated user id
(stashed on request.state by `get_current_user`), falling back to the
client IP for unauthenticated endpoints such as register/login.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

limiter = Limiter(key_func=get_remote_address, storage_uri=get_settings().REDIS_URL)


def user_key(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


def chat_limit(_request: Request | None = None) -> str:
    return f"{get_settings().RATE_LIMIT_CHAT_PER_MIN}/minute"


def api_limit(_request: Request | None = None) -> str:
    return f"{get_settings().RATE_LIMIT_API_PER_HOUR}/hour"
