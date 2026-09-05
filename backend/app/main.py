"""FastAPI application factory (PROJECT_PLAN.md §4).

Run as:
    uv run uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 3001
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.logging import RequestIDMiddleware, configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # DB engine/session and Redis clients are wired up in Steps 2–4; re-assert the
    # JSON logging config here because uvicorn applies its log config after import.
    configure_logging()
    yield


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
    return app


app = create_app()
