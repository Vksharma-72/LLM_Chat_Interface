"""Auth endpoints: register, login, refresh (rotation), logout, me (§7)."""

from fastapi import APIRouter, Depends, Request
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis
from app.api.errors import ApiError
from app.core.config import get_settings
from app.core.limiter import api_limit, limiter, user_key
from app.db.base import utcnow
from app.db.repositories import RefreshTokenRepository, UserRepository
from app.models import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    TokenRequest,
    UserResponse,
)
from app.services.rate_limit import enforce_login_rate_limit
from app.services.security import (
    TokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    user_id_from_payload,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _issue_auth_response(db: AsyncSession, user: User) -> AuthResponse:
    """Mint an access token and persist a fresh refresh-token row (§3)."""
    refresh_token, jti, expires_at = create_refresh_token(user.id)
    await RefreshTokenRepository(db).create(user.id, jti=jti, expires_at=expires_at)
    return AuthResponse(
        access_token=create_access_token(user.id),
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


def _decode_refresh_token(token: str) -> dict:
    try:
        return decode_token(token, "refresh")
    except TokenExpiredError as exc:
        raise ApiError(401, "token_expired", "Refresh token has expired") from exc
    except TokenError as exc:
        raise ApiError(401, "invalid_token", "Invalid refresh token") from exc


@router.post("/register", response_model=AuthResponse, status_code=201)
@limiter.limit(api_limit, key_func=user_key)
async def register(
    request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> AuthResponse:
    settings = get_settings()
    if not settings.REGISTRATION_ENABLED:
        raise ApiError(403, "registration_disabled", "Registration is currently disabled")

    users = UserRepository(db)
    if await users.get_by_email(body.email):
        raise ApiError(409, "duplicate_email", "An account with this email already exists")
    if await users.get_by_username(body.username):
        raise ApiError(409, "duplicate_username", "This username is already taken")

    user_count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    try:
        user = await users.create(
            email=body.email,
            username=body.username,
            password_hash=hash_password(body.password),
            is_admin=settings.FIRST_USER_IS_ADMIN and user_count == 0,
        )
    except IntegrityError as exc:  # concurrent registration race → constraint
        raise ApiError(409, "duplicate_email", "An account with these details already exists") from exc
    return await _issue_auth_response(db, user)


@router.post("/login", response_model=AuthResponse)
@limiter.limit(api_limit, key_func=user_key)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AuthResponse:
    await enforce_login_rate_limit(request, redis, body.username_or_email)

    users = UserRepository(db)
    identifier = body.username_or_email.strip()
    user = await users.get_by_username(identifier)
    if user is None:
        user = await users.get_by_email(identifier)
    if (
        user is None
        or not user.is_active
        or not verify_password(body.password, user.password_hash)
    ):
        raise ApiError(401, "invalid_credentials", "Incorrect username/email or password")

    await users.touch_last_login(user)
    return await _issue_auth_response(db, user)


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit(api_limit, key_func=user_key)
async def refresh(
    request: Request, body: TokenRequest, db: AsyncSession = Depends(get_db)
) -> RefreshResponse:
    payload = _decode_refresh_token(body.refresh_token)
    user_id = user_id_from_payload(payload)

    repo = RefreshTokenRepository(db)
    row = await repo.get_by_jti(str(payload.get("jti", "")))
    if row is None or row.revoked:
        raise ApiError(401, "invalid_token", "Refresh token has been revoked")
    if row.expires_at <= utcnow():
        raise ApiError(401, "token_expired", "Refresh token has expired")

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise ApiError(401, "invalid_token", "Invalid refresh token")

    await repo.revoke(str(payload["jti"]))  # rotation: old jti dies with this call
    refresh_token, jti, expires_at = create_refresh_token(user.id)
    await repo.create(user.id, jti=jti, expires_at=expires_at)
    return RefreshResponse(
        access_token=create_access_token(user.id), refresh_token=refresh_token
    )


@router.post("/logout", status_code=204)
@limiter.limit(api_limit, key_func=user_key)
async def logout(
    request: Request, body: TokenRequest, db: AsyncSession = Depends(get_db)
) -> None:
    payload = _decode_refresh_token(body.refresh_token)
    await RefreshTokenRepository(db).revoke(str(payload.get("jti", "")))


@router.get("/me", response_model=UserResponse)
@limiter.limit(api_limit, key_func=user_key)
async def auth_me(request: Request, user: User = Depends(get_current_user)) -> User:
    return user
