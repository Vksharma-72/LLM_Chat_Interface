"""HTTP hardening middlewares (S9): security headers and request-body cap."""

import json

MAX_BODY_BYTES = 1_000_000  # 1 MB — chat messages are capped at 16k chars upstream

SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
]


class SecurityHeadersMiddleware:
    """Appends hardening headers to every HTTP response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend(SECURITY_HEADERS)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Rejects requests whose declared body exceeds the path's cap (413 envelope).

    Normal API paths are capped at max_bytes (1 MB); file-upload paths get the
    larger upload_max_bytes so multipart files can pass through.
    """

    def __init__(
        self,
        app,
        max_bytes: int = MAX_BODY_BYTES,
        upload_max_bytes: int | None = None,
        upload_paths: tuple[str, ...] = ("/api/attachments",),
    ):
        self.app = app
        self.max_bytes = max_bytes
        self.upload_max_bytes = upload_max_bytes or max_bytes
        self.upload_paths = upload_paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        limit = (
            self.upload_max_bytes
            if scope.get("path", "") in self.upload_paths
            else self.max_bytes
        )
        content_length = int(headers.get(b"content-length", b"0") or 0)
        if content_length > limit:
            body = json.dumps(
                {"error": {"code": "payload_too_large", "message": "Request body too large"}}
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        *SECURITY_HEADERS,
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
