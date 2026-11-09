# 架构

本文件按需求 §3.0 展开。阶段 2 已经落地的只有图中的进程边界、FastAPI 骨架、Next.js BFF 和 Compose 定义。模型转发、账本和支付还没有接入。

## 进程

```text
浏览器 / API 调用方
    │
    ▼
Nginx（TLS、安全头、4MB 体积限制）
    ├── / 、/api/*  → Next.js（官网、控制台、后台；BFF 转发 Cookie）
    ├── /healthz、/readyz、/v1/* → FastAPI
    │
FastAPI
    ├── PostgreSQL 16（业务库 forge，后续含账本）
    ├── Redis 7（限流、队列；财务状态不以 Redis 为准）
    ├── ARQ worker（邮件、关单、对账、预扣释放、链上确认轮询）
    └── LiteLLM v1.106.5
            └── 上游供应商 / 自建推理
                    支付适配器（海外：Stripe + USDT 托管网关）
```

开发编排见 `deploy/docker-compose.yml`。生产编排不把 PostgreSQL、Redis 和 LiteLLM 映射到公网，并强制关闭 mock。

## 后端分层

`apps/api/app` 目前分为：

- `core`：配置、时钟、结构化日志、脱敏、错误信封、请求 ID、就绪探针
- `api`：路由只做解析和响应组装
- `db`：SQLAlchemy 模型与 Alembic
- `worker.py`：ARQ 入口

后续领域目录按 `auth / users / billing / payments / providers / models / gateway / admin / audit / notifications / ops` 增加。每个领域内部是 router → service → repository。资金变更只能在 service 的事务里提交。

## 请求与凭证

五类凭证分开：

1. LiteLLM master key，只在环境变量和 LiteLLM 进程。
2. 上游供应商密钥，只进 LiteLLM 或以后的 Secret Manager。
3. LiteLLM 虚拟 Key，只在平台内部。
4. 用户公开 API Key，业务后端签发，只存摘要。
5. 登录会话，服务端会话表，HttpOnly Cookie。阶段 3 实现。

浏览器业务请求走 BFF：`/api/*` → FastAPI。`/v1/*` 不走 BFF，避免流式被 Node 缓冲。

统一业务响应：`{ ok, data, error, request_id }`。错误码使用需求附录 A，5xx 不返回堆栈。

## 已实现与未实现

已实现：应用工厂、生产环境拒绝 mock 和演示模型、`/healthz`、`/readyz`、`/api/meta`、请求 ID、4MB 体积上限、日志脱敏、身份相关表的迁移、注册登录与 RBAC、ARQ 探活任务、官网页面和 BFF。业务路径不带版本段，见 ADR-004。

未实现：注册登录、RBAC 校验、API Key、模型目录、LiteLLM 转发、预扣账本、支付、管理后台、官网内容页。这些页面在前端标记为「未启用」。
