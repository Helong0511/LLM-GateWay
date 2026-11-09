"""真实客户端 IP 解析。

链路约定（三处必须同时成立，缺一处就会退化成「全站同一个 IP」）：

1. nginx 在**所有** location（含 `/v1/`）写入 `X-Real-IP` 与 `X-Forwarded-For`；
2. uvicorn 以 `--proxy-headers --forwarded-allow-ips=<nginx 网段>` 启动，
   由它把 `scope["client"]` 改写为最右侧可信地址；
3. Next 的 BFF 透传 `x-forwarded-for`（见 `apps/web/src/app/api/[...path]/route.ts`）。

所以这里优先信任已经被 uvicorn 处理过的 `request.client`，其次才是原始头。
"""

from __future__ import annotations

from starlette.requests import Request


def client_ip(request: Request) -> str:
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    if isinstance(host, str) and host:
        return host
    # 没有 uvicorn 代理头处理时的兜底：XFF 最右侧是最近一跳代理写入的真实地址。
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[-1]
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return ""
