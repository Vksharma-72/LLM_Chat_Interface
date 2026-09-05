"""User profile endpoints (§7): get/update me, password change, 30-day usage."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.errors import ApiError
from app.core.limiter import api_limit, limiter, user_key
from app.db.repositories import ApiUsageRepository, UserRepository
from app.models import User
from app.schemas.auth import UserResponse
from app.schemas.user import PasswordChangeRequest, UsageDay, UsageResponse, UserUpdateRequest
from app.services.security import hash_password, verify_password

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
@limiter.limit(api_limit, key_func=user_key)
async def get_me(request: Request, user: User = Depends(get_current_user)) -> User:
    return user


@router.put("/me", response_model=UserResponse)
@limiter.limit(api_limit, key_func=user_key)
async def update_me(
    request: Request,
    body: UserUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if body.username != user.username:
        existing = await UserRepository(db).get_by_username(body.username)
        if existing is not None and existing.id != user.id:
            raise ApiError(409, "duplicate_username", "This username is already taken")
        user.username = body.username
        await db.flush()
    return user


@router.put("/me/password", status_code=204)
@limiter.limit(api_limit, key_func=user_key)
async def change_password(
    request: Request,
    body: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(body.current_password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    await db.flush()


@router.get("/usage", response_model=UsageResponse)
@limiter.limit(api_limit, key_func=user_key)
async def get_usage(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageResponse:
    """Daily token/request totals for the last 30 days, zero-filled (§7)."""
    today = datetime.now(UTC).date()
    start = today - timedelta(days=29)
    rows = await ApiUsageRepository(db).list_for_user_since(user.id, start)
    by_date = {row.date: row for row in rows}

    days: list[UsageDay] = []
    for offset in range(30):
        day = start + timedelta(days=offset)
        row = by_date.get(day)
        days.append(
            UsageDay(
                date=day,
                tokens=row.total_tokens if row else 0,
                requests=row.total_requests if row else 0,
            )
        )
    return UsageResponse(days=days)
