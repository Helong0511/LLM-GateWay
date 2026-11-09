# 算力中转站（ForgeAPI）

统一接入大模型 API 的业务平台：官网 / 客户控制台 / 管理后台 / OpenAI 兼容转发 / 账本与支付。

| 入口 | 地址 |
|------|------|
| 前端 | `http://127.0.0.1:3000` |
| API 健康检查 | `http://127.0.0.1:8000/healthz` |
| 经 Nginx（开发 compose） | `http://127.0.0.1:8080` |
| Mailpit（开发邮件） | `http://127.0.0.1:8025` |

---

## 启动参数（环境变量）

配置入口：仓库根目录 `.env`（从 `.env.example` 复制）。业务进程通过 pydantic-settings 读取；Compose 用 `--env-file .env`。

### 必需

| 变量 | 说明 | 开发示例 |
|------|------|----------|
| `APP_ENV` | `development` / `staging` / `production` | `development` |
| `OPERATING_MODE` | `overseas`（海外）或 `mainland`（大陆） | `overseas` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | PostgreSQL 账号库名 | `forge` / `forge-dev-only` / `forge` |
| `DATABASE_URL` | 异步库连接（`postgresql+asyncpg://...`） | 见 `.env.example` |
| `REDIS_URL` | Redis 连接 | `redis://127.0.0.1:6379/0` |
| `SESSION_SECRET` | 会话密钥，≥32 字节 | 开发口令带 `dev-only` |
| `ENCRYPTION_MASTER_KEY` | 上游凭证加密主密钥，≥32 字节；丢失无法解密已存 Key | 同上 |
| `LITELLM_MASTER_KEY` | LiteLLM 主密钥 | `sk-dev-only-...` |
| `LITELLM_BASE_URL` | LiteLLM 地址 | `http://127.0.0.1:4000` |

### 可选（常用）

| 变量 | 说明 | 默认/示例 |
|------|------|-----------|
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `CORS_ORIGINS` | 浏览器允许来源，逗号分隔 | `http://127.0.0.1:3000,http://localhost:3000` |
| `API_INTERNAL_URL` | 前端 BFF 反代后端地址 | 本机 `http://127.0.0.1:8000`；Compose 内 `http://api:8000` |
| `PUBLIC_APP_URL` | 对外站点根地址（邮件链接等） | `http://127.0.0.1:3000` |
| `MOCK_PAYMENTS_ENABLED` | 模拟支付 | 开发 `true`；生产必须 `false` |
| `DEMO_MODELS_ENABLED` | 演示模型 | 开发 `true`；生产必须 `false` |
| `SESSION_IDLE_HOURS` | 登录空闲超时（小时，滑动续期） | 默认 `12` |
| `SESSION_ABSOLUTE_HOURS` | 登录绝对上限（小时，到期必须重登） | 默认 `168`（7 天） |
| `PG_DUMP_PATH` | `pg_dump` 可执行文件路径；空则自动查找 | 可空 |
| `BACKUP_DOCKER_IMAGE` | 本机无 `pg_dump` 时一次性 Docker 回退镜像 | `postgres:16.10-alpine` |
| `BACKUP_ALLOW_DOCKER` | 是否允许 Docker 回退备份 | 默认 `true`（生产 compose 默认 `false`） |

备份优先级：本机/`PG_DUMP_PATH` 的 `pg_dump` →（若允许）Docker 临时容器 → 应用内 SQL 逻辑备份（`.sql`，无外部工具时仍可用）。
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` / `SMTP_TLS` | 发信 | 开发可接 Mailpit `127.0.0.1:1025` |
| `REDIS_PASSWORD` | Redis 口令（生产 compose 使用） | 生产必填 |
| `API_HOST` / `API_PORT` | 后端监听（进程配置） | `0.0.0.0` / `8000` |
| `HOLD_TTL_SECONDS` / `PAYMENT_TTL_SECONDS` | 预扣 / 订单超时秒数 | `600` / `1800` |
| `DEFAULT_MODEL_INPUT_PRICE` / `DEFAULT_MODEL_OUTPUT_PRICE` | 上游无单价时同步写入的建议价（每 token） | `0.00000100` / `0.00000200` |
| `USDT_*` / `STRIPE_WEBHOOK_SECRET` | 支付与回调相关 | 见 `.env.example` 与代码配置 |

### 进程命令行参数

| 进程 | 命令 | 主要参数 |
|------|------|----------|
| API | `uvicorn app.main:app` | `--host 0.0.0.0` `--port 8000`；开发可加 `--reload` |
| Worker | `arq app.worker.WorkerSettings` | 无额外 CLI；读同一套 `.env` / Redis |
| Web 开发 | `next dev` | `--port 3000` |
| Web 生产 | `next start` 或镜像内 `node server.js` | `--port 3000`；镜像构建需 `NEXT_OUTPUT=standalone` |
| 迁移 | `alembic upgrade head` | 在 `apps/api` 下执行；**不会**随容器首次启动自动跑 |

`APP_ENV=production` 时，进程会拒绝：开发口令（含 `dev-only` / `change-me`）、`MOCK_PAYMENTS_ENABLED=true`、`DEMO_MODELS_ENABLED=true`。

---

## 本机 Windows

### 环境要求

- Python **3.12**、[uv](https://github.com/astral-sh/uv)
- Node.js **22**；前端锁 **pnpm 10.15.1**（不要用 `npx pnpm`，会拉到 pnpm 12）
- **有 Docker**：可用 Compose 起整栈或只起依赖（见 2A / 2B）
- **无 Docker**：本机安装 PostgreSQL、Redis 等，见下一节「不用 Docker 启动」
- 可选：GNU Make（本仓库 `Makefile` 在无 make 时用下面原生命令即可）

### 1. 准备配置

在仓库根目录（PowerShell）：

```powershell
Copy-Item .env.example .env
# 按需改 .env；开发口令仅本机使用
```

### 2A. 整栈 Docker（推荐）

```powershell
docker compose --env-file .env -f deploy/docker-compose.yml up --build
```

首次或需要改表时，另开终端执行迁移：

```powershell
cd apps\api
python -m uv sync
python -m uv run alembic upgrade head
```

访问：`http://127.0.0.1:3000`、`http://127.0.0.1:8000/healthz`。

停止：

```powershell
docker compose --env-file .env -f deploy/docker-compose.yml down
```

### 2B. 混合开发（依赖用 Docker，API / Web 本机跑）

只起依赖（示例：可在 compose 中按需 `up` 指定服务）：

```powershell
docker compose --env-file .env -f deploy/docker-compose.yml up -d postgres redis mailpit litellm
```

如果要启动邮件服务器（Windows）
```powershell
winget install axllent.mailpit
mailpit
```

确认 `.env` 中：

- `DATABASE_URL=...@127.0.0.1:5432/...`
- `REDIS_URL=redis://127.0.0.1:6379/0`
- `LITELLM_BASE_URL=http://127.0.0.1:4000`
- `API_INTERNAL_URL=http://127.0.0.1:8000`
- `CORS_ORIGINS` 含前端来源

后端（PowerShell，仓库根或 `apps\api`）：

```powershell
cd apps\api
python -m uv sync
python -m uv run alembic upgrade head
python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Worker（另开终端）：

```powershell
cd apps\api
python -m uv run arq app.worker.WorkerSettings
```

前端（另开终端）：

```powershell
cd apps\web
npm exec --yes pnpm@10.15.1 install
# 可选：在 apps\web\.env.local 写 API_INTERNAL_URL=http://127.0.0.1:8000
npm exec --yes pnpm@10.15.1 dev
```

Windows 本地 **不要** 设置 `NEXT_OUTPUT=standalone`（仅镜像构建使用）。

### 本机检查

```powershell
python -m uv sync --project apps/api
python -m uv run --project apps/api pytest
cd apps\api; python -m uv run ruff check app alembic; python -m uv run mypy app

cd apps\web
npm exec --yes pnpm@10.15.1 test
npm exec --yes pnpm@10.15.1 lint
```

---

## 不用 Docker 启动（本机 / 服务器通用）

适合：本机无 Docker，或 Ubuntu 上直接装包跑进程。需自行安装并常驻 **PostgreSQL 16**、**Redis 7**；LiteLLM、Mailpit 可选（无 LiteLLM 时模型转发依赖你自己的上游；无 Mailpit 时开发邮件可先空着 `SMTP_HOST`）。

### 依赖对照

| 组件 | 端口（默认） | 是否必需 | 说明 |
|------|--------------|----------|------|
| PostgreSQL | `5432` | 必需 | 库 `forge`；若跑 LiteLLM 再加库 `litellm` |
| Redis | `6379` | 必需 | Worker / 会话相关 |
| API（uvicorn） | `8000` | 必需 | 业务后端 |
| Worker（arq） | — | 必需 | 探活、过期预扣、关单、审计链校验 |
| Web（Next） | `3000` | 必需 | 官网 + 控制台 + 后台 |
| LiteLLM | `4000` | 可选 | 网关转发上游；`LITELLM_BASE_URL` 指向它 |
| Mailpit / SMTP | `1025` / `8025` | 可选 | 开发收信；生产换真实 SMTP |

`.env` 仍指向本机环回地址（与 `.env.example` 一致），例如：

```env
DATABASE_URL=postgresql+asyncpg://forge:forge-dev-only@127.0.0.1:5432/forge
REDIS_URL=redis://127.0.0.1:6379/0
LITELLM_BASE_URL=http://127.0.0.1:4000
API_INTERNAL_URL=http://127.0.0.1:8000
CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
```

### Windows：安装依赖（无 Docker）

1. 安装 [PostgreSQL 16](https://www.postgresql.org/download/windows/)，记住超级用户口令。  
2. 安装 [Redis for Windows](https://github.com/tporadowski/redis/releases) 或 WSL2 内的 Redis，并启动服务。  
3. 安装 Python 3.12、uv、Node.js 22。  
4. 用 `psql`（或 pgAdmin）建库与用户（口令与 `.env` 一致）：

```sql
CREATE USER forge WITH PASSWORD 'forge-dev-only';
CREATE DATABASE forge OWNER forge;
CREATE DATABASE litellm OWNER forge;
```

也可对超级用户执行仓库内 `sql/00_create_litellm_database.sql`（仅 `CREATE DATABASE litellm;`），再自行建 `forge`。

5. （可选）LiteLLM：另开终端，用官方方式起代理，配置可参考 `deploy/litellm/config.yaml`，监听 `127.0.0.1:4000`，`LITELLM_MASTER_KEY` 与 `.env` 一致。  
6. （可选）Mailpit：从 [Mailpit Releases](https://github.com/axllent/mailpit/releases) 下载 Windows 二进制，例如：

```powershell
mailpit.exe
# SMTP 1025，Web UI 8025
```

### Ubuntu 22.04.5：安装依赖（无 Docker）

```bash
sudo apt update
sudo apt install -y postgresql redis-server git curl ca-certificates

# Python 3.12（若系统源无 3.12，用 deadsnakes 或 pyenv）
# Node.js 22：按 NodeSource / nvm 安装
# uv：curl -LsSf https://astral.sh/uv/install.sh | sh

sudo systemctl enable --now postgresql redis-server

sudo -u postgres psql <<'SQL'
CREATE USER forge WITH PASSWORD 'forge-dev-only';
CREATE DATABASE forge OWNER forge;
CREATE DATABASE litellm OWNER forge;
SQL
# 生产请换成高强度口令，并改 pg_hba / 只监听内网
```

（可选）LiteLLM / Mailpit：自行用 pip/二进制安装，监听本机 `4000` / `1025`。

### 启动业务进程（Windows PowerShell）

仓库根目录先准备 `.env`，再开 **3～4** 个终端：

```powershell
# 终端 1：API
cd apps\api
python -m uv sync
python -m uv run alembic upgrade head
python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2：Worker
cd apps\api
python -m uv run arq app.worker.WorkerSettings

# 终端 3：前端
cd apps\web
npm exec --yes pnpm@10.15.1 install
# 可选：apps\web\.env.local 写入 API_INTERNAL_URL=http://127.0.0.1:8000
npm exec --yes pnpm@10.15.1 dev
```

生产形态（本机或跳板试跑，无 `--reload`）：

```powershell
cd apps\api
python -m uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
# Worker 同上
cd apps\web
npm exec --yes pnpm@10.15.1 build
npm exec --yes pnpm@10.15.1 start
# 不要设置 NEXT_OUTPUT=standalone（那是 Docker 镜像构建用的）
```

### 启动业务进程（Ubuntu bash）

```bash
cp -n .env.example .env   # 已有则跳过
# 编辑 .env：生产改口令，APP_ENV=production，关掉 mock/演示模型

cd apps/api
uv sync
uv run alembic upgrade head

# 终端 / tmux / systemd 分别常驻：
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
uv run arq app.worker.WorkerSettings

cd ../web
# 开发：
npm exec --yes pnpm@10.15.1 install
npm exec --yes pnpm@10.15.1 dev
# 生产：
npm exec --yes pnpm@10.15.1 install
npm exec --yes pnpm@10.15.1 build
npm exec --yes pnpm@10.15.1 start -- --port 3000
```

前面建议用 Nginx 反代 `3000`（静态/站点）与 `8000`（仅内网或按路径转发）；防火墙只放行 **22 / 80 / 443**，**不要**把 `5432` / `6379` 暴露到公网。

验证：

```bash
curl -sS http://127.0.0.1:8000/healthz
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000
```

### 无 Docker 时的注意点

- 迁移必须手动执行：`uv run alembic upgrade head`。  
- Worker 不启则过期预扣释放、超时关单、审计链定时任务不会跑。  
- 不装 LiteLLM 时，管理后台仍可配供应商直连；网关若依赖 LiteLLM，需改配置或自备兼容代理。  
- 生产无 Docker 时同样禁止开发口令与 mock；`SESSION_SECRET` / `ENCRYPTION_MASTER_KEY` 等必须换高强度值。
- 改环境变量时须同步：`.env` / `.env.example`、`deploy/docker-compose*.yml`、README/部署文档与相关测试。

---

## 服务器 Ubuntu 22.04.5（Docker 方式）

推荐用 Docker Compose 部署生产编排；防火墙只放行 **22 / 80 / 443**，数据库与 Redis **不要**对公网暴露。无 Docker 时见上一节。

### 1. 系统准备

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
# Docker 官方安装文档：https://docs.docker.com/engine/install/ubuntu/
# 安装后把当前用户加入 docker 组，重新登录后再跑 compose

# 建议（运维）：提高文件句柄、开启 BBR、统一 NTP
sudo sysctl -w fs.file-max=65535
# 持久化与 BBR/NTP 按机房规范配置
```

### 2. 拉取代码并配置

```bash
git clone <本仓库地址> forgeapi
cd forgeapi
cp .env.example .env
chmod 600 .env
# 编辑 .env：生产必须改掉所有口令与密钥，并设置：
#   APP_ENV=production
#   MOCK_PAYMENTS_ENABLED=false
#   DEMO_MODELS_ENABLED=false
#   REDIS_PASSWORD=...
#   DATABASE_URL / REDIS_URL 指向 compose 服务名（见 docker-compose.prod.yml）
#   PUBLIC_APP_URL / CORS_ORIGINS 改为真实域名（含 https）
#   邮件改为真实 SMTP + SPF/DKIM/DMARC
```

### 3. 启动生产栈

```bash
docker compose --env-file .env -f deploy/docker-compose.prod.yml up --build -d
```

迁移（在能访问库的环境执行一次；可用临时/一次性容器或本机带 uv 的跳板）：

```bash
cd apps/api
# 若宿主机有 Python 3.12 + uv，且 DATABASE_URL 能连上 postgres 服务网络：
uv run alembic upgrade head
```

或用 API 镜像进入后迁移（按你机上实际镜像名/网络调整）：

```bash
docker compose --env-file .env -f deploy/docker-compose.prod.yml run --rm api \
  uv run --frozen --no-dev alembic upgrade head
```

### 4. 验证与日常

```bash
curl -sS http://127.0.0.1/healthz   # 经 Nginx 时按实际反代路径调整；API 容器内为 :8000/healthz
docker compose --env-file .env -f deploy/docker-compose.prod.yml ps
docker compose --env-file .env -f deploy/docker-compose.prod.yml logs -f api worker web
```

停止：

```bash
docker compose --env-file .env -f deploy/docker-compose.prod.yml down
```

### 编排文件对照

| 文件 | 用途 |
|------|------|
| `deploy/docker-compose.yml` | 开发：Mailpit、本机端口映射、mock 由 `.env` 决定 |
| `deploy/docker-compose.staging.yml` | 叠在开发文件上，环境改为 staging |
| `deploy/docker-compose.prod.yml` | 生产：强制关 mock/演示模型；Postgres/Redis 不映射公网；Nginx `80/443` |

生产镜像内默认命令：

- API：`uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Worker：`arq app.worker.WorkerSettings`
- Web：`node server.js`（端口 3000）

---

## 文档

- 需求：`docs/软件需求.MD`
- 部署说明：`docs/DEPLOYMENT.md`
- 运行手册：`docs/RUNBOOK.md`
- 架构与其它：`docs/`

---

## 模型计价与接入指南

### 时区规范（核心！）

**所有时段时间字段一律用 UTC。** 时区只影响 weekday 和节假日判定。

为什么全用 UTC：
- 服务器多时区、用户多时区、日志统一
- DeepSeek 英文文档直接写 UTC 时段，中文文档的北京时间只是给中国开发者看的
- 上游 API 按请求完成时刻的实际时间计费，不受你服务器位置影响
- DeepSeek Peak 换算：北京时间 9:00 = UTC 01:00，北京时间 18:00 = UTC 10:00

### 时段定价配置

#### 内部统一格式

所有上游格式（LiteLLM / OpenRouter / DeepSeek / 阿里云 / 火山方舟）在解析后都归一化为下面这个内部统一格式：

```json
{
  "timezone": "UTC",
  "rules": [
    {
      "label": "off_peak",
      "exclude_holidays": true,
      "holidays_region": "CN",
      "windows": [
        {"hours_utc": "01:00-04:00", "weekdays": [1,2,3,4,5]},
        {"hours_utc": "06:00-10:00", "weekdays": [1,2,3,4,5]},
        {"hours_utc": "00:00-00:00", "weekdays": [6,7]}
      ],
      "overrides": {
        "input_token":  {"unit_price": "0.00000015", "cost_price": "0.00000015"},
        "output_token": {"unit_price": "0.00000060", "cost_price": "0.00000060"}
      }
    }
  ]
}
```

#### 时段窗口三种等价写法

引擎全支持，任选一种：

| 写法 | 格式 | 示例 |
|---|---|---|
| `hours_utc` | "HH:MM-HH:MM" 字符串 | `"01:00-04:00"` |
| `utc_start` / `utc_end` | "HHMM" 字符串（OpenRouter 新格式） | `"utc_start": "0100", "utc_end": "0400"` |
| `utc_start` / `utc_end` | 整数分钟 0-1440（OpenRouter 旧格式） | `"utc_start": 60, "utc_end": 240` |

半开区间 [start, end)，可跨午夜（start > end），start == end 视为全天。

#### weekday 多种写法

统一转为 ISO 数字（周一=1，周日=7），全支持：

| 写法 | 示例 |
|---|---|
| ISO 数字 | `[1,2,3,4,5]` |
| 英文缩写 | `["mon","tue","wed"]` |
| 中文 | `["周一","周二"]` |
| 缺省 | 每天 |

#### DeepSeek 完整 UTC 配置示例（含节假日排除）

DeepSeek 官方（2025-11）：Peak = UTC 01:00-04:00 + 06:00-10:00 周一至周五（**不含中国法定节假日**），Off-Peak = 其他所有时段（含周末 + 节假日全天）。Off-Peak 价 = Peak 价的一半。

```json
{
  "timezone": "UTC",
  "rules": [
    {
      "label": "off_peak",
      "exclude_holidays": true,
      "holidays_region": "CN",
      "windows": [
        {"hours_utc": "00:00-01:00", "weekdays": [1,2,3,4,5]},
        {"hours_utc": "04:00-06:00", "weekdays": [1,2,3,4,5]},
        {"hours_utc": "10:00-00:00", "weekdays": [1,2,3,4,5]},
        {"hours_utc": "00:00-00:00", "weekdays": [6,7]}
      ],
      "overrides": {
        "input_token":  {"unit_price": "0.00000015", "cost_price": "0.00000015"},
        "output_token": {"unit_price": "0.00000060", "cost_price": "0.00000060"},
        "cached_input_token": {"unit_price": "0.000000003", "cost_price": "0.000000003"}
      }
    }
  ]
}
```

注意：`exclude_holidays: true` 时，规则在法定节假日不匹配。内置 2024-2026 中国法定节假日表（含调休工作日）。**DeepSeek 是唯一明确排除中国法定节假日的主流模型**，OpenRouter、阿里云、火山方舟都不支持节假日判定。

#### 计费优先级

基础 tier 价 → 时段 overrides 覆盖 → 默认价兜底。

- overrides 里只写需要改的 meter，没写的继承基础档
- publish 时漏传 input_token/output_token → 用平台默认价补齐
- cost_price 缺失 → 用 unit_price 兜底（防毛利报表 0 成本污染）

### 阶梯计费配置

阿里云百炼首创，核心规则：**同一请求的所有 Token 按最高命中档单价结算，不是分段叠加。**

例：某模型 input_token 有三档 `tier_min_tokens=0 / 32001 / 128001`，请求 200K tokens → 全部 200K 按 128001 档单价结算（不是 0-32K 按 0 档、32K-128K 按 32001 档、128K+ 按 128001 档分段叠加）。

#### 阿里云百炼 qwen3-max 完整阶梯配置

```json
{
  "currency": "CNY",
  "meters": [
    {"meter": "input_token",  "unit_price": "0.0000025", "cost_price": "0.0000010", "min_billable_units": 0, "tier_min_tokens": 0},
    {"meter": "input_token",  "unit_price": "0.0000040", "cost_price": "0.0000016", "min_billable_units": 0, "tier_min_tokens": 32001},
    {"meter": "input_token",  "unit_price": "0.0000070", "cost_price": "0.0000028", "min_billable_units": 0, "tier_min_tokens": 128001},
    {"meter": "output_token", "unit_price": "0.0000100", "cost_price": "0.0000040", "min_billable_units": 0, "tier_min_tokens": 0},
    {"meter": "output_token", "unit_price": "0.0000160", "cost_price": "0.0000064", "min_billable_units": 0, "tier_min_tokens": 32001},
    {"meter": "output_token", "unit_price": "0.0000280", "cost_price": "0.0000112", "min_billable_units": 0, "tier_min_tokens": 128001}
  ],
  "schedule_rules": null
}
```

同一 meter 内 tier_min_tokens 不能重复，必须升序。没有时段规则时 `schedule_rules` 设为 `null`。

### 主流模型计价速查（2025 年 11 月最新）

| 模型 | 计价方式 | Peak 时段 | Off-Peak | 阶梯 | 时区 | 节假日 |
|---|---|---|---|---|---|---|
| **DeepSeek Flash** | 时段 | UTC 01:00-04:00 + 06:00-10:00 工作日 | Peak ÷ 2 | 无 | UTC | 排除中国法定节假日 |
| **DeepSeek V4-Pro** | 时段 | 同上 | Peak ÷ 2 | 无 | UTC | 排除中国法定节假日 |
| **OpenRouter** | 自定义 | 由 `utc_start/utc_end` + `utc_days` 定义 | 自定义 | 支持 `min_prompt_tokens` | UTC | 不支持 |
| **阿里云百炼 Qwen3-Max** | 阶梯 | 无 | — | 0-32K / 32K-128K / 128K-256K 三档 | — | — |
| **火山方舟 DeepSeek-V3** | 固定价 | 无 | — | 部分模型有长输入阶梯 | — | — |

**DeepSeek 价格明细（USD，每百万 Token）：**

| 模型 | 时段 | 输入（Cache Miss） | 输出 | 输入（Cache Hit） |
|---|---|---|---|---|
| DeepSeek Flash | Peak | $0.30 | $1.20 | $0.006 |
| DeepSeek Flash | Off-Peak | $0.15 | $0.60 | $0.003 |
| DeepSeek V4-Pro | Peak | $1.32 | $3.96 | $0.044 |
| DeepSeek V4-Pro | Off-Peak | $0.66 | $1.98 | $0.022 |

**阿里云百炼 qwen3-max 阶梯价格（人民币，每百万 Token）：**

| 区间 | 输入单价 | 输出单价 |
|---|---|---|
| 0 < Token ≤ 32K | 2.5 元 | 10 元 |
| 32K < Token ≤ 128K | 4.0 元 | 16 元 |
| 128K < Token ≤ 256K | 7.0 元 | 28 元 |

### 第三方模型接入完整指南

#### 命名规范

系统里有三个关键名称，各司其职，**不能混用**：

| 字段 | 位置 | 规范 | 示例 |
|---|---|---|---|
| `Provider.name` | providers 表 | 小写英文，无空格，上游官方品牌名 | `deepseek` / `openrouter` / `aliyun` / `volcengine` / `moonshot` / `zhipu` |
| `ModelCatalog.upstream_name` | model_catalog 表 | 上游真实模型 ID（上游 API 调用时 `model` 参数值） | `deepseek-flash` / `qwen3-max` / `doubao-pro-32k` |
| `ModelCatalog.public_name` | model_catalog 表 | 对外展示名（前端给用户看的） | `DeepSeek Flash V4.1` / `千问 3 Max` |

**命名红线：**
- Provider.name 不要写公司全称（不要 `volcengine.com`，写 `volcengine`）
- upstream_name 必须和上游 `/v1/chat/completions` 里 `model` 参数值**完全一致**，否则 404
- public_name 不要包含价格信息（会变），写模型能力/代际

#### 接入步骤

```
Step 1: Admin 后台添加 Provider
├─ POST /api/admin/providers
├─ body: {
│   "name": "deepseek",
│   "kind": "cloud",
│   "base_url": "https://api.deepseek.com",
│   "protocol": "openai",
│   "api_key": "sk-xxx..."
│ }
└─ 返回 provider_id

Step 2: 同步上游模型列表和建议价
├─ POST /api/admin/providers/{provider_id}/sync
├─ 系统自动调用上游 /v1/models
├─ 解析单价 + 时段规则（自动识别 LiteLLM / OpenRouter 格式）
├─ 写入 model_catalog.upstream_input_price / upstream_output_price / upstream_schedule_rules
└─ 返回发现的模型列表

Step 3: Admin 发布生效价
├─ POST /api/admin/prices
├─ body: {
│   "model_id": "uuid",
│   "currency": "USD",
│   "meters": [
│     {"meter": "input_token", "unit_price": "0.00000015", "cost_price": "0.00000015"},
│     {"meter": "output_token", "unit_price": "0.00000060", "cost_price": "0.00000060"}
│   ],
│   "schedule_rules": { ... }   // 可选，时段定价模型填；阶梯定价也可叠加
│ }
└─ 系统自动补 cost_price（= unit_price 如果漏传）
    + input_token / output_token 缺失时用平台默认价补

Step 4: 启用模型
├─ Admin 后台把模型状态改成 published
└─ 用户端 console/models 可见，网关可调用
```

#### 上游格式自动解析

同步时系统自动识别以下上游定价格式：

| 上游 | 单价字段 | 时段格式 |
|---|---|---|
| **LiteLLM** | `input_cost_per_token` / `output_cost_per_token` / `*_per_million` | `off_peak_pricing`（内嵌 `input_cost_per_token` + `output_cost_per_token`） |
| **OpenRouter 旧格式** | `pricing.prompt` / `pricing.completion` | `pricing.overrides[].time_based` 含 `utc_start`（整数分钟）/`utc_end` / `utc_days` |
| **OpenRouter 新格式** | `pricing.prompt` / `pricing.completion` | `pricing.overrides[].utcStart`（HHMM 整数）/`utcEnd` / `utcDays`，或 `input_modalities[].pricing[].utc_start`（HHMM 字符串） |
| **每百万 Token** | `*_cost_per_million_tokens` / 数值 ≥ 0.01 | 自动除以 1,000,000 换算为每 Token 单价 |

#### 常见坑

1. **人民币 vs 美元**：上游如果给的是人民币价（阿里云、火山方舟），publish 时 `currency` 设为 `CNY`，系统**不会**自动换算。如果你的平台用 USD 计费，需要手动按汇率转换。
2. **节假日只对 DeepSeek 生效**：只有 DeepSeek 明确排除中国法定节假日（`exclude_holidays: true`）。OpenRouter、阿里云、火山方舟的时段规则都是纯时间判定，不看节假日。
3. **全量 vs 分段**：阿里云百炼是"**全量按最高档**"，不是分段叠加。阶梯配置时 `tier_min_tokens` 是阈值下限（包含），不是区间起点。
4. **OpenRouter min_prompt_tokens**：OpenRouter 的 `minPromptTokens` 条件（长输入加价）会被解析成阶梯计费的 `tier_min_tokens`。
5. **跨时段请求**：计费用**请求完成时刻**匹配时段（参考 DeepSeek 官方规则"请求完成时间对应计费时段"）。预扣（reserve）用请求发起时刻，结算（finish）用请求完成时刻，差额自动在 `settle_hold` 里退回或补扣。
6. **时区偏移**：服务器在 UTC，用户在东八区，weekday 判定用**上游声明的时区**（`schedule_rules.timezone` 字段）。DeepSeek 官方时段直接给的是 UTC 时间，所以填 `"UTC"` 就行。**不要因为你服务器在北京就改成 Asia/Shanghai。**
7. **缓存价**：DeepSeek 有 cache hit 单独计价，publish 时加 `cached_input_token` 这个 meter。如果不填，`calculate()` 会回退用 `input_token` 价。
8. **cost_price 为 0**：如果 cost_price 设为 0 或漏传，系统自动用 unit_price 兜底。**不要手动设 0**，会污染毛利报表。
9. **OpenRouter 两套时间表示**：整数分钟（0-1440，旧格式）和 HHMM 字符串（`"0100"`，新格式）引擎全支持，publish 时任选一种。
10. **时段优先级**：多个 rule 都命中时，数组里排在最前面的优先。写 DeepSeek 配置时把 off_peak 写在前面（它窗口多、覆盖广），peak 写在后面（默认兜底）。

### FAQ

**Q: 上游格式不在自动解析列表里怎么办？**  
A: 在 `app/providers/upstream_pricing.py::extract_schedule_rules()` 加一个解析分支，或者 Admin 手动 publish 时直接填内部统一格式的 `schedule_rules` JSON。

**Q: 没有时段规则的模型怎么计费？**  
A: 全量按基础 tier 价结算，`schedule_rules` 设为 `null` 或不填。

**Q: 阶梯和时段能叠加吗？**  
A: 能。基础 tier 价先被时段 overrides 覆盖，`calculate()` 再按新价 + tier 规则选档。例：某模型长输入档 input_token $0.000007，off-peak 覆盖成 $0.0000035，请求 200K tokens → 全部按 $0.0000035 × 200K 结算。

**Q: 怎么确定上游模型的真实 upstream_name？**  
A: 调上游 `GET /v1/models` 接口看每个条目的 `id` 字段。那就是 upstream_name。

**Q: 阶梯计费的 tier_min_tokens 怎么算区间？**  
A: `tier_min_tokens` 是**包含型下限**。引擎取 `tier_min_tokens ≤ input_tokens` 的最高档。所以基础档是 `tier_min_tokens=0`，下一档是 > 0 的阈值。阿里云百炼 32K 阈值对应 `tier_min_tokens=32001`（因为规则是 32K < Token ≤ 128K）。

**Q: 代码层面哪些文件负责这些逻辑？**  
A:
- 时段匹配引擎：`apps/api/app/billing/schedule.py::match_schedule`
- 计费核心（阶梯选档 + 数值计算）：`apps/api/app/billing/pricing.py::calculate`
- 发布生效价（支持多档 + 时段规则）：`apps/api/app/billing/pricing.py::PricingService.publish`
- 上游同步解析（自动识别 LiteLLM/OpenRouter 格式）：`apps/api/app/providers/upstream_pricing.py::extract_schedule_rules`
- Admin 发布 API：`apps/api/app/billing/router.py::publish_price`



-- 审计链衔接检查。只读。
-- 内容哈希要由服务重新计算，对应 GET /api/admin/audit/verify。
-- 这里只检查序号连续，以及后一条的 prev_hash 等于前一条的 content_hash。


-- 登录页是同一个：http://127.0.0.1:3000/login。进去之后再打开对应地址。

-- 客户端


-- 管理员端

-- 下面是 cloudflare 的 验证密码
-- 765869276
-- 566936963
-- 539551895
-- 611437015
-- 095100467
-- 928659920
-- 108030536
-- 164095746


## 测试API-KEY
```txt
lvFLoISXYg5FgwrY7YDNB355Lb3AqSPes1MzOudei7EhZK1N
```

## 模拟邮件服务
```txt
winget install axllent.mailpit
mailpit
```