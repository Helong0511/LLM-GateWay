"""沙箱网关状态。测试和开发确认回调前，主动查单读的就是这里。"""

from __future__ import annotations


class StripeGateway:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, object]] = {}


class UsdtGateway:
    def __init__(self) -> None:
        self.orders: dict[str, dict[str, object]] = {}
