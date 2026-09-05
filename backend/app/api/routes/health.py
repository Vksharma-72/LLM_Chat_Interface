"""GET /health — unauthenticated liveness probe (PROJECT_PLAN.md §7)."""

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": get_settings().APP_VERSION}
