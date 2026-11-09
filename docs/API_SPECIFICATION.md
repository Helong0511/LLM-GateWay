# API 规格

业务 API 前缀是 `/api`，不带版本段。公开模型 API 使用 OpenAI 协议路径 `/v1`，错误体是 `{ "error": { "message", "type", "code" } }`，不用业务信封。存活和就绪探针不带业务前缀。见 ADR-004。

成功与失败都使用：

```json
{ "ok": true, "data": {}, "error": null, "request_id": "..." }
```

失败时 `ok` 为 false，`error` 含 `code`、`message`、`details`。5xx 的 message 固定为「服务内部错误」，不带堆栈。响应头带 `X-Request-Id`。调用方传入的 `X-Request-Id` 只有匹配 `^[A-Za-z0-9._-]{8,64}$` 时才沿用。

## 已实现

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/healthz` | 进程存活。不检查数据库 |
| GET | `/readyz` | 检查 PostgreSQL 与 Redis。未就绪返回 503 `DEPENDENCY_UNAVAILABLE`，`data.checks` 给出 postgres/redis |
| GET | `/api/meta` | 产品名、运营模式、环境、mock 开关。不含密钥 |
| POST | `/api/auth/register` | 注册。密码用 Argon2id。邮件未配置时 `email_delivery` 为 `unconfigured`，响应不含令牌 |
| POST | `/api/auth/verify-email` | 校验邮箱令牌。令牌只存 SHA-256 |
| POST | `/api/auth/login` | 登录。连续 5 次失败锁定 15 分钟。开启二次验证时不发会话 Cookie |
| POST | `/api/auth/totp/verify` | 用登录挑战和验证码换取会话 Cookie |
| POST | `/api/auth/logout` | 作废当前会话并清除 Cookie |
| GET | `/api/auth/me` | 当前用户。未登录 401 |
| POST | `/api/auth/forgot-password` | 不暴露邮箱是否存在。邮件未配置时明确返回未配置 |
| POST | `/api/auth/reset-password` | 重置密码并作废全部会话 |
| POST | `/api/auth/change-password` | 修改密码并作废其他会话 |
| POST | `/api/auth/email-change` | 向新邮箱发送确认令牌 |
| POST | `/api/auth/email-change/confirm` | 确认新邮箱 |
| POST | `/api/auth/totp/setup` | 生成二次验证种子，只返回一次 |
| POST | `/api/auth/totp/enable` | 校验后开启，并返回一次恢复码 |
| POST | `/api/auth/bootstrap` | 用初始化口令摘要创建唯一超级管理员，成功后口令文件改名作废 |
| GET | `/api/admin/whoami` | 需要 `admin:access`。普通用户 403 |
| GET | `/api/admin/overview` | 需要 `admin:access`。返回用户、供应商、已上架模型、密钥、订单、流水和审计条数 |
| GET | `/api/admin/audit` | 需要 `admin:access`。审计列表，默认 20 条，最多 100 条。不含密钥 |
| GET | `/api/admin/audit/verify` | 需要 `admin:access`。按序号重算哈希链。断裂时返回 `ok: false` 和 `broken_seq` |
| GET | `/api/admin/users` | 需要 `admin:access`。用户列表，含状态和角色名，不含密码 |
| POST | `/api/admin/users/{user_id}/status` | 需要 `user:ban`。把正常账号冻结，或把冻结账号恢复。不能冻结自己，并写审计 |
| POST | `/api/admin/users/{user_id}/roles` | 需要 `rbac:assign`。不能分配超级管理员。成功后追加一条审计 |
| POST | `/api/keys` | 创建 API Key。明文只在这次响应里返回，库存 SHA-256。空的 `allowed_models` 不能调用任何模型 |
| GET | `/api/keys` | 列出当前用户的密钥。只返回前缀，不含明文 |
| POST | `/api/keys/{key_id}/revoke` | 吊销自己的密钥。别人的密钥返回 404。吊销后立刻不能通过校验 |
| GET | `/api/console/summary` | 今日与本月调用次数、token、成功率、平均延迟和 14 天趋势来自已结算记录。没有记录时成功率和延迟为空。余额是账本可用余额，无流水时为 `0.00000000` |
| GET | `/api/usage` | 当前用户的调用记录。分页默认 20、上限 100，返回 page/page_size/total/pages。排序带 id 作为次键，避免同时间戳翻页漏数或重复。模型筛选、结算状态筛选。看不到别人的记录 |
| GET | `/api/billing` | 当前用户的结算币余额、预扣、冻结、可用余额和流水。金额为 8 位小数字符串 |
| GET | `/api/payments/products` | 当前运营模式结算币下已启用的充值套餐。目录为空时补上 10、50、100 三档，已有同金额则不重复插入 |
| GET | `/api/payments/orders` | 当前用户自己的充值订单 |
| GET | `/api/admin/orders` | 需要 `admin:access`。全部客户的充值订单，带邮箱，不含支付密钥 |
| GET | `/api/admin/refunds` | 需要 `admin:access`、`refund:request` 或 `refund:execute` 之一。退款列表，并标明当前账号能否发起或执行 |
| GET | `/api/admin/ledger` | 需要 `admin:access`。全部客户余额和最近流水，只读 |
| GET | `/api/admin/usage` | 需要 `admin:access`。全部客户调用记录，不含密钥和提示词 |
| GET | `/api/admin/keys` | 需要 `admin:access`。全部密钥只含前缀、配额和所属邮箱，不含哈希和明文 |
| POST | `/api/admin/keys/{key_id}/revoke` | 需要 `user:ban`。强制吊销并写审计，立即不能通过校验 |
| POST | `/api/admin/keys/{key_id}/limits` | 需要 `admin:access`。修改每分钟请求、token、并发和预算。空预算表示不设上限 |
| GET | `/api/admin/deployments` | 需要 `admin:access`。已上架模型的部署 |
| POST | `/api/admin/deployments/{deployment_id}/status` | 需要 `model:publish`。停用后该模型不能再被调用 |
| GET | `/api/admin/crypto` | 需要 `admin:access`。USDT 收款尾数和制裁地址，地址只显示首尾，不含私钥 |
| GET | `/api/admin/health` | 需要 `admin:access`。PostgreSQL 与 Redis 状态，不含连接串 |
| GET | `/api/notifications/preferences` | 当前用户的余额预警开关和两条预警线 |
| PATCH | `/api/notifications/preferences` | 保存预警。较高线不能低于较低线。可用余额落到任一条线都会写通知 |
| POST | `/api/tickets` | 当前用户提交工单。分类为 billing、technical、refund、chain、other |
| GET | `/api/tickets` | 当前用户自己的工单 |
| GET | `/api/tickets/{ticket_id}` | 当前用户自己的工单和回复。别人的工单返回 404 |
| POST | `/api/tickets/{ticket_id}/messages` | 当前用户回复自己的工单。已关闭不能回复 |
| GET | `/api/admin/tickets` | 需要 `admin:access`。全部工单 |
| GET | `/api/admin/tickets/{ticket_id}` | 需要 `admin:access`。工单和回复 |
| POST | `/api/admin/tickets/{ticket_id}/messages` | 需要 `admin:access`。回复并修改状态，写审计 |
| POST | `/api/invoices` | 按当前用户已完成订单申请发票。金额取自订单，同一订单只能申请一次 |
| GET | `/api/invoices` | 当前用户自己的发票申请 |
| GET | `/api/admin/invoices` | 需要 `admin:access` 或 `refund:request`。全部申请，并标明能否审核 |
| POST | `/api/admin/invoices/{invoice_id}/status` | 需要 `refund:request`。把 requested 改为 issued 或 rejected。不生成 PDF |
| GET | `/api/announcements` | 已发布公告 |
| GET | `/api/announcements/{slug}` | 已发布公告正文。未发布返回 404 |
| POST | `/api/admin/announcements` | 需要 `admin:access`。创建未发布公告 |
| POST | `/api/admin/announcements/{announcement_id}/publish` | 需要 `admin:access`。发布或撤回 |
| POST | `/api/admin/coupons` | 需要 `admin:access`。创建赠送金额券 |
| GET | `/api/admin/coupons` | 需要 `admin:access`。券码、金额和已用次数 |
| POST | `/api/coupons/redeem` | 当前用户兑换。记一笔 bonus 流水。同一用户同一券只入账一次 |
| GET | `/api/admin/margin` | 需要 `admin:access` 或 `refund:request`。用户费用、供应商成本和订单对账状态计数 |
| GET | `/api/admin/routes` | 需要 `admin:access`。已上架且部署未停用的模型及其供应商 |
| GET | `/api/admin/settings` | 需要 `admin:access`。运行开关和限额。不含连接串和密钥 |
| GET | `/api/admin/content-safety` | 需要 `admin:access`。开关和审计记录。记录只有类别和摘要哈希 |
| POST | `/api/admin/content-safety` | 需要 `admin:access`。打开或关闭。默认关闭 |
| GET | `/api/admin/tasks` | 需要 `admin:access`。已知任务、最近记录和失败记录 |
| POST | `/api/admin/tasks/ping` | 需要 `admin:access`。执行探活并记一条成功记录 |
| GET | `/api/admin/backups` | 需要 `admin:access`。backups 目录里的 dump 和本机是否有 pg_dump |
| POST | `/api/admin/backups` | 需要 `admin:access`。调用 pg_dump。没有恢复接口 |
| POST | `/api/payments/orders` | 创建充值订单。需要 `Idempotency-Key`。同一用户同一键重复提交返回第一次的结果；内容不同返回 409 |
| POST | `/api/payments/mock/confirm` | 开发环境确认模拟支付并入账。生产环境拒绝模拟支付 |
| POST | `/api/payments/stripe/webhook` | Stripe 回调。先验签，再主动查单，然后入账。不走浏览器来源检查 |
| POST | `/api/payments/usdt/notify` | USDT 回调。先验签和来源 IP，再主动查单。少付不入账，制裁地址冻结不入账 |
| POST | `/api/admin/prices` | 需要 `model:publish`。发布当前运营模式结算币的价格版本 |
| POST | `/api/admin/payments/reconcile` | 按渠道账单核对已入账金额，不符标为 disputed |
| POST | `/api/admin/refunds` | 需要 `refund:request`。发起退款。USDT 只能退回原付款地址 |
| POST | `/api/admin/refunds/{refund_id}/review` | 另一名财务复核。不能复核自己发起的退款 |
| POST | `/api/admin/refunds/{refund_id}/execute` | 需要 `refund:execute`。执行退款。执行人不能是发起人 |
| GET | `/api/notifications` | 当前用户的站内通知 |
| POST | `/api/notifications/refresh` | 扫描 7 天内到期的密钥。可用余额低于阈值时写一条余额通知，同一用户不重复堆叠 |
| POST | `/api/notifications/{notification_id}/read` | 把自己的通知标为已读。别人的通知返回 404 |
| GET | `/api/auth/profile` | 显示名、时区、语言 |
| PATCH | `/api/auth/profile` | 更新资料。时区必须是合法时区名 |
| GET | `/api/auth/devices` | 当前用户的登录设备 |
| GET | `/openapi.json` | 非生产环境可用。生产环境关闭文档 |
| POST | `/api/admin/providers` | 需要 `provider:manage`。创建前做 SSRF 校验。私有地址拒绝；自建和 Ollama 必须先进入白名单；云元数据地址一律拒绝 |
| GET | `/api/admin/providers` | 供应商列表。凭证只返回掩码，不含明文 |
| POST | `/api/admin/providers/{provider_id}/credentials` | 信封加密保存上游凭证，响应只有掩码。旧的有效凭证改为撤销 |
| POST | `/api/admin/allowlist` | 审批自建端点主机或地址，并写审计 |
| POST | `/api/admin/providers/{provider_id}/sync` | 拉取上游 `GET /v1/models`。新模型状态为待确认，不覆盖已有行，不填写能力 |
| GET | `/api/admin/models` | 需要 `model:publish`。管理侧模型目录，含未上架行 |
| POST | `/api/admin/models/{model_id}/publish` | 上架必须显式给出是否支持流式和 Embeddings。其余能力保持空 |
| POST | `/api/admin/providers/{provider_id}/probe` | 连接、生成、流式、超时、鉴权和缺模型探测。只存状态，不存提示词、密钥和上游正文 |
| GET | `/api/console/models` | 登录用户可见的已上架模型。空能力表示未确认，不带价格 |
| GET | `/v1/models` | 用 API Key 列出该密钥可以调用的已上架模型 |
| POST | `/v1/chat/completions` | 用用户密钥鉴权，转发给 LiteLLM 时换成主密钥。没有生效价格时费用为 0。有价格时先预扣，成功按用量结算，失败释放预扣。流式中断记为 cancelled 并释放并发槽 |
| POST | `/v1/embeddings` | 仅当模型明确支持 Embeddings 时转发。未确认或不支持返回 404 |
| POST | `/v1/images/generations` 及音频、文件、批处理 | 返回 501，消息为「该接口尚未开放」 |

请求体超过 4MB（存在 Content-Length 时）返回 400 `VALIDATION_ERROR`。

错误码基线见需求附录 A：VALIDATION_ERROR、UNAUTHENTICATED、INVALID_API_KEY、FORBIDDEN、INSUFFICIENT_BALANCE、NOT_FOUND、IDEMPOTENCY_CONFLICT、RATE_LIMITED、CONCURRENCY_LIMITED、UPSTREAM_ERROR、DEPENDENCY_UNAVAILABLE、INTERNAL。认证补充 EMAIL_TAKEN、EMAIL_NOT_VERIFIED、ACCOUNT_LOCKED、MAIL_NOT_CONFIGURED、TOKEN_INVALID。

会话 Cookie：开发环境名 `session`，生产环境名 `__Host-session`。HttpOnly、SameSite=Lax。空闲 7 天，绝对 30 天。带 Origin 且不在允许列表中的写请求返回 403。

## 尚未实现

工单、发票、公告和其余管理模块的页面。审计哈希链已接到分配角色和供应商变更；运营概览只统计现有表。`/v1` 的每分钟请求、每分钟 token 和并发上限由当前进程内的计数器执行，还没有接到 Redis。余额预警在账本启用前不会发出。没有上架模型时，密钥不能完成一次真实调用。本机没有运行 LiteLLM。管理后台页面还没有供应商配置表单。

幂等键 `Idempotency-Key` 已在 BFF 转发头中预留，服务端存储尚未实现。

前端类型由 `openapi-typescript` 从 `/openapi.json` 生成到 `apps/web/src/lib/api/schema.ts`，不手写请求类型。
