FROM python:3.12.11-slim-bookworm

# 管理端备份依赖 pg_dump（与数据库主版本尽量接近即可）
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
EXPOSE 8000
# --proxy-headers + --forwarded-allow-ips：让 request.client.host 变成真实客户端 IP。
# 少这一行，注册限流会退化成「全站每小时 20 次」，Key / USDT 的 IP 白名单全部失效。
# API 容器不允许对外发布端口（见 deploy/docker-compose.prod.yml），因此信任内网代理。
#
# --workers：单进程在 async I/O 下够用，但 JSON 编解码 / 加解密会串行，且一崩全断。
# 每多一个 worker，PG 连接数就多一份 (DB_POOL_SIZE + DB_MAX_OVERFLOW)，
# 调整 workers 时必须同步下调这两个值（compose 里已按 2 workers 调过）。
CMD ["sh", "-c", "exec uv run --frozen --no-dev uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers \"${UVICORN_WORKERS:-2}\" --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-*}\" --no-server-header"]
