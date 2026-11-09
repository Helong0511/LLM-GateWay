"""请求关联 ID、体积上限与基础安全响应头；过期会话顺带清 Cookie。"""

from __future__ import annotations

import re
from uuid import uuid4

import structlog
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import failure

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def resolve_request_id(header_value: str | None) -> str:
    if header_value and _REQUEST_ID.fullmatch(header_value):
        return header_value
    return str(uuid4())


def _delete_cookie_header(name: str, *, secure: bool) -> tuple[str, str]:
    parts = [f"{name}=", "Path=/", "Max-Age=0", "HttpOnly", "SameSite=lax"]
    if secure:
        parts.append("Secure")
    return ("set-cookie", "; ".join(parts))


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        request_id = resolve_request_id(headers.get("x-request-id"))
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["request_id"] = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)

        content_length = headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.max_body_bytes:
            request = Request(scope)
            response = failure(request, 400, "VALIDATION_ERROR", f"请求体超过 {self.max_body_bytes} 字节限制")
            await response(scope, receive, send)
            structlog.contextvars.clear_contextvars()
            return

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                raw_headers.append((b"x-request-id", request_id.encode("ascii")))
                raw_headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                    ]
                )
                req_state = scope.get("state")
                if isinstance(req_state, dict):
                    clear_cookie = bool(req_state.get("clear_session_cookie"))
                else:
                    clear_cookie = bool(getattr(req_state, "clear_session_cookie", False))
                if clear_cookie:
                    app = scope.get("app")
                    settings = getattr(getattr(app, "state", None), "settings", None)
                    if settings is not None:
                        secure = bool(settings.cookie_secure or settings.app_env == "production")
                        name, value = _delete_cookie_header(settings.session_cookie_name, secure=secure)
                        raw_headers.append((name.encode("latin-1"), value.encode("latin-1")))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            structlog.contextvars.clear_contextvars()
