"""JSON structured logging with request IDs (PROJECT_PLAN.md §4).

Every log line is a single JSON object on stdout. Each HTTP request gets a
request ID (incoming `X-Request-ID` or a fresh UUID), carried in a ContextVar
so log records anywhere in the request's async context include it, and echoed
back in the response header.
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

logger = logging.getLogger("app.request")

# LogRecord attributes that are not caller-provided `extra` fields.
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "color_message"}


class JsonFormatter(logging.Formatter):
    """Render each record as one JSON object with a `request_id` when set."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            entry["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging() -> None:
    """Route all loggers (app + uvicorn) through a single JSON handler. Idempotent."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    # Request lines are already emitted by RequestIDMiddleware as JSON.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class RequestIDMiddleware:
    """Pure-ASGI middleware: assign/propagate a request ID and log the request as JSON."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        request_id = (
            headers.get(b"x-request-id", b"").decode("latin-1") or uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log = logger.error if status_code >= 500 else logger.info
            log(
                "%s %s -> %s",
                scope.get("method", "?"),
                scope.get("path", "?"),
                status_code,
                extra={
                    "http_method": scope.get("method", "?"),
                    "http_path": scope.get("path", "?"),
                    "http_status": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(token)
