# 部署

本机（Windows）没有 Docker，也没有 GNU make。下面的编排是按文件写好的，容器启动没有在这台机器上执行。

## 开发

1. 安装 Docker、Node 22、pnpm、Python 3.12、uv。
2. 复制 `.env.example` 为 `.env`。开发口令只用于本机。
3. 在仓库根目录执行：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up --build
```

4. 健康检查：`GET http://127.0.0.1:8000/healthz` 应返回 `ok: true`。`/readyz` 在 PostgreSQL 和 Redis 就绪后返回 200，否则返回 503，并在 `data.checks` 里标明哪一个依赖不可用。
5. 浏览器打开 `http://127.0.0.1:3000` 或经 Nginx 的 `http://127.0.0.1:8080`。页面上的状态必须来自后端。Mailpit 界面在 `http://127.0.0.1:8025`。
6. 迁移：`cd apps/api && uv run alembic upgrade head`。容器首次启动不会自动迁移，避免在未确认的库上改表。

没有 Docker 时，可以只跑后端单测和前端单测。那不能代替整栈启动。

## 环境

| 文件 | 用途 |
| --- | --- |
| `deploy/docker-compose.yml` | 开发。含 Mailpit、本机端口、mock 由 `.env` 决定 |
| `deploy/docker-compose.staging.yml` | 叠加到开发文件上，把 API 环境改成 staging |
| `deploy/docker-compose.prod.yml` | 独立生产文件。强制关闭 mock 和演示模型，不映射数据库端口 |

生产必须另备高强度 `SESSION_SECRET`、`ENCRYPTION_MASTER_KEY`、`LITELLM_MASTER_KEY`、`POSTGRES_PASSWORD`、`REDIS_PASSWORD`。进程检测到开发口令会拒绝启动。

登录会话时效由 `SESSION_IDLE_HOURS`（默认 12）与 `SESSION_ABSOLUTE_HOURS`（默认 168）控制，须在 `.env` / `.env.example`、开发/预发/生产 compose 中同步配置；改一项时不要漏其它环境。

## 镜像版本

- postgres:16.10-alpine
- redis:7.4.2-alpine
- nginx:1.27.5-alpine
- axllent/mailpit:v1.21.8
- ghcr.io/berriai/litellm:v1.106.5
- python:3.12.11-slim-bookworm
- node:22.14.0-alpine

这些标签按发布记录填写，本机没有执行 `docker pull`，不能当成已验证可拉取。

## 容量与系统

第一阶段单机可运行。需求中的生产起步档是应用机 4C8G、数据机 4C16G，海外机房可选香港、新加坡或美西。Ubuntu 上需要把文件句柄调到 65535，开启 BBR，统一 NTP，防火墙只放行 22/80/443。这些还没有在目标机器上执行。

管理端「备份」优先 `pg_dump`（API 镜像已装 `postgresql-client`）；本机无客户端时可设 `PG_DUMP_PATH` / `BACKUP_ALLOW_DOCKER`，再不行则用应用内 SQL 逻辑导出（`.sql`）。无一键在线恢复；恢复演练仍属运维手工流程。

## 监控与运维接口

- `GET /metrics`：Prometheus 抓取端点。`METRICS_TOKEN` 非空时需 `Authorization: Bearer <token>`；
  nginx 默认不代理该路径，只在容器网络内可达。抓取与告警配置见 `deploy/prometheus/alerts.yml`。
- `GET /api/admin/ledger/reconcile`：按流水重算余额快照并列出差异（只读，`admin:access`）；
  加 `?apply=true` 会修复并写审计链，需要 `ledger:adjust`（默认只有 superadmin）。
  建议每月或每次资金类故障后跑一次只读比对。
- 备份加密：设置 `BACKUP_ENCRYPTION_KEY` 后，导出即加密为 `.dump.enc` / `.sql.enc` 并删除明文。
  恢复前用 `BACKUP_ENCRYPTION_KEY=... python scripts/decrypt_backup.py <file>.enc` 解密。
  密钥丢失等于备份不可恢复，必须与数据库口令分开保管。
- worker 每日 04:20 执行 `purge_litellm_logs`，按 `LITELLM_LOG_RETENTION_DAYS`（默认 30 天）
  分批清理 LiteLLM 的日志表；未配置 `LITELLM_DATABASE_URL` 时自动跳过。

## 超管初始化

`scripts/init_admin.py` 用 CSPRNG 生成 `init_` 令牌，只打印一次，并把 SHA-256 写到 `.data/admin_init_token.sha256`。阶段 3 才会用它创建超级管理员。摘要文件已存在时脚本拒绝覆盖。
