"""结构化日志。生产环境输出 JSON，开发环境输出控制台可读格式。"""

from __future__ import annotations

import logging

import structlog

from app.core.config import Settings
from app.core.redaction import redact_event


class AccessLogNoiseFilter(logging.Filter):
    """过滤未登录会话探测产生的 401 访问日志噪音。

    /api/auth/me 是前端页面导航时的登录态探测：未登录时返回 401 属预期
    语义而非异常，无需在访问日志中刷屏。已登录请求（200）与真实鉴权
    失败的 API（其他路径）不受影响。
    """

    QUIET_PATHS = ("/api/auth/me",)

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            args = record.args
            if isinstance(args, tuple) and len(args) >= 5:
                path = str(args[2])
                status = str(args[4])
            else:
                parts = record.getMessage().split('"')
                if len(parts) < 3:
                    return True
                request_line = parts[1].split()
                if len(request_line) < 2:
                    return True
                path = request_line[1]
                status = parts[2].strip().split()[0]
            if status == "401" and path.split("?", 1)[0] in self.QUIET_PATHS:
                return False
        except Exception:
            return True
        return True


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")

    logging.getLogger("uvicorn.access").addFilter(AccessLogNoiseFilter())

    renderer: structlog.types.Processor
    if settings.json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_event,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
