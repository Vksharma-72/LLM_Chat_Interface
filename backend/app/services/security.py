"""Password hashing and JWT issue/decode (PROJECT_PLAN.md §7, §2).

Access tokens carry `type=access` and live ACCESS_TOKEN_MINUTES; refresh tokens
carry `type=refresh`, live REFRESH_TOKEN_DAYS, and a `jti` that the auth route
persists in `refresh_tokens` so rotation/revocation is possible.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings


class TokenError(Exception):
    """A token is malformed, has the wrong type, or fails verification."""

    code = "invalid_token"
    message = "Invalid token"


class TokenExpiredError(TokenError):
    code = "token_expired"
    message = "Token has expired"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _encode(payload: dict[str, Any]) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return _encode(
        {
            "sub": str(user_id),
            "type": "access",
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        }
    )


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str, datetime]:
    """Return (jwt, jti, expires_at) — the caller persists the jti row."""
    settings = get_settings()
    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_DAYS)
    token = _encode(
        {
            "sub": str(user_id),
            "type": "refresh",
            "jti": jti,
            "iat": now,
            "exp": expires_at,
        }
    )
    return token, jti, expires_at


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and verify a JWT of the expected type; raises TokenError family."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError from exc
    if payload.get("type") != expected_type:
        raise TokenError
    return payload


def user_id_from_payload(payload: dict[str, Any]) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise TokenError from exc
