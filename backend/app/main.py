"""FastAPI application factory (PROJECT_PLAN.md §4).

Run as:
    uv run uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 3001
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.users import router as users_router
from app.core.config import Settings, get_settings
from app.core.logging import RequestIDMiddleware, configure_logging
from app.db.session import get_engine


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

    # Every error leaves as {"error": {"code", "message"}} (§7, §10).
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    return app


app = create_app()
