"""API error envelope: every error response is {"error": {"code", "message"}}
with no stack traces (PROJECT_PLAN.md §7, §10)."""

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

_HTTP_CODE_MAP = {401: "unauthorized", 404: "not_found", 405: "method_not_allowed"}


class ApiError(Exception):
    """Raise from routes/deps to emit the standard error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def _envelope(code: str, message: str) -> dict[str, object]:
    return {"error": {"code": code, "message": message}}


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message),
        headers=exc.headers,
    )


async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
        for error in exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content=_envelope("validation_error", details or "Validation failed"),
    )


async def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = _HTTP_CODE_MAP.get(exc.status_code, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500, content=_envelope("internal_error", "Internal server error")
    )
