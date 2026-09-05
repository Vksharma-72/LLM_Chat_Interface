"""Application settings loaded from the workspace-root `.env` (PROJECT_PLAN.md §5).

The `.env` file lives at the workspace root (two levels above `backend/`); real
environment variables take precedence over it, which is how tests point the app
at `llmchat_test` / Redis db 1 (see `tests/conftest.py`).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → parents[3] is the workspace root
ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- App ---
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 3001
    APP_ENV: str = "development"
    APP_VERSION: str = "0.1.0"

    # --- Data stores ---
    DATABASE_URL: str = "postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat"
    TEST_DATABASE_URL: str = (
        "postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat_test"
    )
    REDIS_URL: str = "redis://localhost:6379/0"
    TEST_REDIS_URL: str = "redis://localhost:6379/1"

    # --- Auth ---
    JWT_SECRET: str  # required — no default, must come from .env
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 60
    REFRESH_TOKEN_DAYS: int = 7

    # --- CORS (comma-separated origins) ---
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Feature flags ---
    REGISTRATION_ENABLED: bool = True
    FIRST_USER_IS_ADMIN: bool = True

    # --- Rate limits ---
    RATE_LIMIT_CHAT_PER_MIN: int = 20
    RATE_LIMIT_API_PER_HOUR: int = 120
    RATE_LIMIT_LOGIN_PER_15MIN: int = 5
    MAX_MESSAGE_CHARS: int = 16000

    # --- LLM upstream ---
    LLM_API_URL: str = "http://localhost:8000/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_TIMEOUT_SECONDS: int = 120
    LLM_MAX_CONCURRENT: int = 2
    LLM_LIVE_TEST: bool = False
    LLM_VISION_ENABLED: bool = True

    # --- File attachments ---
    UPLOAD_DIR: str = "uploads"
    UPLOAD_MAX_FILE_MB: int = 100
    DOC_MAX_CHARS: int = 100_000

    # --- Mock LLM server ---
    MOCK_LLM_PORT: int = 8001
    MOCK_LLM_REPLY: str = "This is a mock reply from the mock LLM server."
    MOCK_VISION_REPLY: str = "I can see the image."
    MOCK_LLM_LATENCY_MS: int = 0
    MOCK_LLM_CHUNKS: int = 12

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
