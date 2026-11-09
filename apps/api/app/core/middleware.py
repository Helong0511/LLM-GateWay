"""请求关联 ID、体积上限与基础安全响应头；过期会话顺带清 Cookie。"""

from __future__ import annotations

import re
import time
from uuid import uuid4

import structlog
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import failure
from app.core.metrics import (
    HTTP_DURATION,
    HTTP_INFLIGHT,
    HTTP_REQUESTS,
    REGISTRY,
    route_label,
)

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class _BodyTooLarge(Exception):
    """内部信号：请求体在流式读取过程中超过上限。"""


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

        method = scope.get("method", "GET")
        route = route_label(scope.get("path", ""))
        started_at = time.perf_counter()
        REGISTRY.add_gauge(HTTP_INFLIGHT, 1.0)

        def record(status: int | None) -> None:
            REGISTRY.add_gauge(HTTP_INFLIGHT, -1.0)
            if status is None:
                return
            REGISTRY.counter(
                HTTP_REQUESTS, {"method": method, "route": route, "status": str(status)}
            )
            REGISTRY.observe(
                HTTP_DURATION, time.perf_counter() - started_at, {"method": method, "route": route}
            )

        content_length = headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.max_body_bytes:
            request = Request(scope)
            response = failure(
                request, 413, "PAYLOAD_TOO_LARGE", f"请求体超过 {self.max_body_bytes} 字节限制"
            )
            record(413)
            await response(scope, receive, send)
            structlog.contextvars.clear_contextvars()
            return

        # Content-Length 可以被省略（chunked），因此必须在读取过程中累计字节数。
        received = 0
        started = False
        status_code: int | None = None
        # 不能在 receive() 里抛异常：FastAPI 会把 body 读取阶段的任意异常
        # 兜底成 HTTPException(400)，超限信号会被吞掉，chunked 请求因此绕过上限。
        # 改为「截断输入 + 丢弃应用响应 + 自回 413」。
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    too_large = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def send_with_id(message: Message) -> None:
            nonlocal started, status_code
            if too_large:
                return  # 应用对截断输入的响应一律丢弃，由下面统一回 413
            if message["type"] == "http.response.start":
                started = True
                status_code = int(message.get("status", 0)) or None
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
            await self.app(scope, limited_receive, send_with_id)
        except _BodyTooLarge:
            # 兼容自定义应用直接抛出信号的路径。
            too_large = True
        finally:
            if too_large and not started:
                request = Request(scope)
                response = failure(
                    request, 413, "PAYLOAD_TOO_LARGE", f"请求体超过 {self.max_body_bytes} 字节限制"
                )
                status_code = 413
                await response(scope, receive, send)
            record(status_code)
            structlog.contextvars.clear_contextvars()
