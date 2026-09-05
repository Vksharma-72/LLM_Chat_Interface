"""FastAPI application factory (PROJECT_PLAN.md §4).

Run as:
    uv run uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 3001
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from app.api.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    rate_limit_exceeded_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.users import router as users_router
from app.core.config import ROOT_DIR, Settings, get_settings
from app.core.logging import RequestIDMiddleware, configure_logging
from app.db.session import get_engine


class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for client-side routes (§9).

    Unknown /api paths still 404 (JSON envelope) instead of returning HTML.
    """

    def __init__(self, *, index_file: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._index_file = index_file

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api"):
                return FileResponse(self._index_file)
            raise


def _mount_frontend(app: FastAPI) -> None:
    dist_dir = ROOT_DIR / "frontend" / "dist"
    index_file = dist_dir / "index.html"
    if not index_file.is_file():
        return  # frontend not built yet — dev uses the Vite server on :5173
    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    app.mount(
        "/",
        SPAStaticFiles(directory=dist_dir, index_file=index_file, html=True),
        name="frontend",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Re-assert JSON logging on startup: uvicorn applies its log config after import.
    configure_logging()
    yield
    await get_engine().dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    app = FastAPI(
        title="LLM Chat Interface",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(conversations_router)
    app.include_router(chat_router)

    # Every error leaves as {"error": {"code", "message"}} (§7, §10).
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    _mount_frontend(app)  # single origin :3001 (API + built frontend, §9)
    return app


app = create_app()
