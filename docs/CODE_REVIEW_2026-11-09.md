# 代码审查报告

- 审查日期：2026-11-09
- 审查对象：`D:/Users/18307/.workbuddy/LLM-GateWay`（commit `a686fed`）
- 代码规模：后端 `apps/api/app` 15,035 行（88 个模块）；前端 `apps/web/src` 13,441 行（含 7,707 行生成的 OpenAPI 类型）
- 审查方式：全量源码阅读（安全基线、网关、账本、支付、后台、BFF）+ ruff / mypy / pytest 实际执行

---

## 总体结论

**当前状态：功能骨架完整、工程质量基线较好，但不具备生产上线条件。**

分层评价：

| 维度 | 评价 | 说明 |
| --- | --- | --- |
| 架构与分层 | 良 | service / repository / router 边界清晰，业务码与 HTTP 层解耦，错误信封统一 |
| 安全设计 | 中上 | 口令 Argon2id、令牌仅存摘要、上游凭证 AES-GCM、SSRF 有 IP 钉扎、退款三方分离、审计哈希链，均属正确做法 |
| 资损控制 | 中 | 三段式预扣 + 幂等键 + 行锁的思路正确，但**兜底路径存在三处断链**（见 P0-2/3/4），实际会冻结用户余额 |
| 支付闭环 | **差** | Stripe / USDT 的「主动查单」是进程内字典占位，真实渠道永远无法入账 |
| 部署正确性 | **差** | 真实客户端 IP 在整条链路上丢失，导致限流、IP 白名单、审计 IP 全部失真 |
| 测试可信度 | 中 | 104 个用例中 6 个失败，失败原因是测试替身被实现绕过，CI 必红 |

问题分布：**P0 阻断 5 项 / P1 高 7 项 / P2 中 8 项 / P3 低 3 项**。

---

## 一、阻断级问题（P0）

### P0-1 支付渠道未闭环，「主动查单」是内存占位

**现象**：`ingest_stripe` / `ingest_usdt` 的入账前置条件是「回调内容与主动查单结果一致」，但主动查单读取的是进程内字典。

**证据**：
- `app/payments/gateways.py:6-13`：`StripeGateway.sessions` / `UsdtGateway.orders` 均为空 `dict`，无任何查单方法。
- `app/payments/service.py:637-643`：下单时写入 `payment_status = "unpaid"`，全仓库无任何位置将其改为 `"paid"`（`grep payment_status` 仅 3 处命中，且无写入路径）。
- `app/payments/service.py:857`：`_stripe_matches` 要求 `query.get("payment_status") == "paid"`，因此**任何 Stripe 回调都必然返回 400「内容与查单结果不一致」**。
- `app/payments/service.py:363-365`：USDT 侧 `usdt.orders` 永远为空，必然返回 503。

**影响**：
1. 除 `mock` 渠道外，真实充值 100% 无法入账，属于收入阻断。
2. 字典存于进程内存，多 worker / 多副本 / 重启后，同一订单的下单与回调落在不同进程时也必然失配。
3. 反向风险：签名正确即可通过验签，真正的支付状态从未向 PSP 核实；一旦补齐字典写入逻辑而忘记核对实付，就会形成「未付款也入账」的资损口子。

**建议**：把 `StripeGateway` / `UsdtGateway` 改为真实 HTTP 客户端（Stripe `GET /v1/checkout/sessions/{id}`、USDT 走链上或服务商查单接口），查单结果落库（`payment_orders.provider_snapshot`），回调只做「验签 + 比对已落库快照」。在网关实现完成前，生产环境应通过启动校验直接禁止 `stripe` / `usdt` 渠道下单，而不是留一个必然失败的入口。

---

### P0-2 定时任务从未被调度，预扣永不过期

**现象**：`release_expired_holds` / `close_expired_payments` 已实现，但没有任何调度配置。

**证据**：
- `app/worker.py:110-117`：`WorkerSettings` 只声明 `functions`，**没有 `cron_jobs`**。
- 全仓库 `grep cron|enqueue_job` 无命中；`ops/platform.py:29-34` 的 `KNOWN_JOBS` 仅是展示用白名单。
- `deploy/docker-compose*.yml` 的 worker 命令为 `arq app.worker.WorkerSettings`，同样不带调度。

**影响**：`HOLD_TTL_SECONDS`（默认 600 秒）在文档与配置中承诺「到期自动释放」，实际永不执行。配合 P0-3，用户被预扣的资金会**永久冻结**，只能人工改库。

**建议**：在 `WorkerSettings` 中补充
`cron_jobs = [cron(release_expired_holds, second=0), cron(close_expired_payments, minute={0,30})]`，
并为 `release_expired` 增加 `LIMIT` 分批（当前一次性 `select` 全表再逐条加锁，积压时会撞 30 秒 `job_timeout`）。

---

### P0-3 上游异常时不释放预扣，余额被长期占用

**现象**：`prepare()` 已 `reserve()` 落预扣，但上游请求失败时没有任何释放路径。

**证据**：
- `app/gateway/service.py:164-222`：`complete()` 的 `try/finally` 只 `release` 并发槽，不触碰账本。
- `app/gateway/service.py:386-396`：`_post()` 在连接失败/超时时 `raise AppError(503, ...)`，直接跳出 `complete()`。
- `app/gateway/router.py:178-180`：路由层捕获 `AppError` 后仅 `commit` 并返回错误信封。
- `app/gateway/service.py:315-352`：`embeddings()` 同样只有 `finally: slots.release(...)`。

**影响**：上游超时（默认可达 60 秒）、502、503 都会留下一条 `status='held'` 的预扣；结合 P0-2，资金不会自动归还。高频重试场景下单个用户的可用余额会被快速吃光，表现为「余额充足但调用全部 402」。

**建议**：在 `complete()` / `embeddings()` 的 `except` 分支调用
`await self._billing().finish(..., http_status=502, chargeable=False)`，
与 `stream()` 的 `finally` 结算保持对称；同时把「异常路径必须结清」写成账本层的断言（例如请求结束时校验 `usage.settlement_status != 'pending'`）。

---

### P0-4 余额不足错误码分裂，争议结算兜底失效

**现象**：账本抛出的错误码与调用方捕获的错误码不是同一个字符串。

**证据**：
- 抛出：`app/billing/ledger.py:82` → `raise AppError(402, "BALANCE_INSUFFICIENT")`
- 捕获：`app/billing/service.py:117` → `if exc.code != "INSUFFICIENT_BALANCE": raise`
- 捕获：`app/billing/ledger.py:268` → `if exc.code != "INSUFFICIENT_BALANCE": raise`
- 默认映射：`app/core/errors.py:15` → `402: "INSUFFICIENT_BALANCE"`
- 测试断言：`tests/api/test_billing.py:279` → `== "BALANCE_INSUFFICIENT"`

**影响**：`settle_hold()` 在「实付超过预扣」且余额不足时本应降级为 `disputed`，实际会把 `AppError` 一路抛出。结果是**上游已成功生成内容、用户却收到 402**，且 `usage_records.settlement_status` 停留在 `pending`、预扣停留在 `held`（叠加 P0-2 即永久占用）。

**建议**：统一为一个常量（建议保留语义更准确的 `BALANCE_INSUFFICIENT`），在 `app/core/errors.py` 中集中定义 `ErrorCode` 枚举并由三处引用，避免字符串字面量再次漂移；同时补一条覆盖「实付超预扣 + 余额不足」的单测。

---

### P0-5 真实客户端 IP 全链路丢失

**现象**：`request.client.host` 在所有入口拿到的都是上游代理容器 IP。

**证据**：
- `apps/api/Dockerfile:16`：`uvicorn ...` 未带 `--proxy-headers` / `--forwarded-allow-ips`。
- `deploy/nginx/nginx.conf:64`：仅在 `location /` 设置 `X-Forwarded-For`，`/v1/` 段完全没有设置；`X-Real-IP` 全局未设置。
- `apps/web/src/app/api/[...path]/route.ts:5-12`：BFF 白名单中不含 `x-forwarded-for` / `x-real-ip`，浏览器路径的真实 IP 在 Next 这一跳被丢弃。
- `app/auth/deps.py:22-25`：`client_ip()` 只读 `request.client.host`。
- `app/gateway/router.py:157`：`ip = request.client.host`。

**影响**（均为真实业务后果）：
1. `REGISTER_IP_HOURLY_LIMIT`（默认 20）退化为**全站每小时 20 次注册**，超过即全员 429，可直接造成注册功能雪崩。
2. API Key 的 `ip_allowlist` 失效：所有请求同 IP —— 白名单含代理 IP 则人人可过，不含则人人被拒。
3. USDT 回调 `USDT_CALLBACK_IPS` 白名单同理失效，`signatures.ip_allowed()` 形同虚设。
4. 审计日志、登录设备、`register_ip` 全部记录错误来源，事后追溯不可用。

**建议**：三处同时修——uvicorn 增加 `--proxy-headers --forwarded-allow-ips=<nginx 网段>`；nginx 为 `/v1/` 补 `X-Forwarded-For` / `X-Real-IP`；BFF 透传 `x-forwarded-for`（或由 Next 追加自身解析结果）。`client_ip()` 改为「可信代理层级内取 XFF 最右非可信地址」，并补一条覆盖多层代理的单测。

---

## 二、高优先级问题（P1）

### P1-1 六个后端测试必然失败：测试替身被实现绕过

`app/main.py:69-73` 无条件创建全局 `upstream_client`，`gateway/router.py:60-73` 同时传入 `transport` 与 `upstream_client`，而 `gateway/service.py:387-390` 优先使用 `upstream_client`。测试通过 `app.state.upstream_transport = httpx.MockTransport(...)` 注入（`tests/api/test_gateway.py:102`、`tests/api/test_billing.py:188`），该注入点实际是死代码。

实测：`6 failed, 98 passed`，失败项为
`test_billing::test_tc_bill_003 / 004 / 005`、`test_billing::test_tc_conc_001`（依赖本机 PostgreSQL，环境缺失时跳过路径也未生效）、`test_gateway::test_tc_gw_publish_and_chat_hide_upstream_secret`、`test_gateway::test_tc_gw_stream_cancel_releases_slot_and_rate_limit`。
根因证据：本机 `curl http://127.0.0.1:4000/healthz` 返回 502，说明用例确实发出了真实网络请求。

**建议**：`_service()` 中令 `transport` 优先于 `upstream_client`（`transport is not None` 时传 `upstream_client=None`），或在 `create_app` 中允许注入 `upstream_client`。修复后 CI 才能真正起到门禁作用。

### P1-2 前端 `proxy.ts` 只透传最后一个 Cookie

`apps/web/src/proxy.ts:27-30` 在循环内使用 `requestHeaders.set("cookie", ...)`，每次迭代覆盖前值。浏览器同时存在 `session` 与 `locale`（`lib/locale.ts:132` 会写入 `locale`）时，只有遍历顺序最后一个 Cookie 被送往 `/api/auth/me`；若顺序不巧，用户切换语言后会被判定未登录并强制跳转登录页。

**建议**：改为 `set("cookie", cookies.map(({name, value}) => `${name}=${value}`).join("; "))`。该循环应移出，构造一次即可。

### P1-3 缺少 CSP / HSTS 等浏览器侧安全响应头

API 侧有 `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy`（`core/middleware.py:62-69`），但 HTML 由 Next 输出，`next.config.ts` 未配置 `headers()`，页面响应无 CSP、无 HSTS、无 `Permissions-Policy`。对含管理后台的站点，缺少 CSP 会放大任何一处 XSS 的后果（虽然当前无 `dangerouslySetInnerHTML`，见 P3 说明）。

**建议**：在 `next.config.ts` 增加 `headers()`：`Strict-Transport-Security`、`Content-Security-Policy`（`default-src 'self'`，按需放行内联样式）、`X-Frame-Options: DENY`、`Permissions-Policy`。

### P1-4 请求体大小限制可被绕过

`core/middleware.py:50-56` 仅当 `Content-Length` 存在且为数字时拒绝。分块传输（`Transfer-Encoding: chunked`）或省略该头时限制完全失效，`request.json()` / `request.arrayBuffer()` 会无上限读入内存。BFF（`apps/web/src/app/api/[...path]/route.ts:47`）同样先 `arrayBuffer()` 全量缓冲，无任何上限。

**建议**：中间件包裹 `receive` 累计字节数，超限即中断并返回 413；BFF 侧校验 `content-length` 并设置上限（与后端 `MAX_BODY_BYTES` 对齐）。

### P1-5 `X-Request-Id` 由客户端决定，且被当作 usage 唯一键

`core/middleware.py:17-20` 接受客户端 `X-Request-Id`（仅校验形状），`gateway/router.py:158` 直接用它作为 `request_id`，`usage_records.request_id` 有唯一约束，`start_usage` 未捕获 `IntegrityError`（`keys/service.py:276-293`）。

后果：客户端只要复用同一个 request id（或与历史值碰撞），第二次请求即 500 `INTERNAL`；日志关联也会被污染。

**建议**：usage 主键改为服务端生成的 UUID，客户端 request id 只作为可检索的附加字段；或至少加 `user_id` 前缀并捕获唯一冲突转为 409。

### P1-6 优惠券计数存在丢更新，可能超发

`app/ops/service.py:450-455`：`if coupon.used_count >= coupon.max_uses: raise` 之后 `coupon.used_count += 1`，读取时未加行锁。两个不同用户并发兑换最后一名额时都读到 `used_count = max_uses - 1`，各自写回 `max_uses`，结果发放 `max_uses + 1` 份奖励；数据库 `ck_coupons_uses`（`used_count <= max_uses`）不会触发，因为两个写入值都合法。

**建议**：改为 `UPDATE coupons SET used_count = used_count + 1 WHERE id = :id AND used_count < max_uses RETURNING used_count`（或 `SELECT ... FOR UPDATE`），以受影响行数判定是否抢到名额。

### P1-7 初始化超管存在并发竞态

`app/auth/service.py:411-435`：先 `count_superadmins() > 0` 判重，再创建用户，最后 `path.replace(consumed)`。两个并发 bootstrap 请求可同时通过计数检查并各自创建超级管理员；文件重命名只影响后续请求，不构成互斥。

**建议**：以数据库唯一约束兜底（例如 `users` 上加「superadmin 唯一」的约束，或在 `audit_chain_lock` 类似的单行表上 `FOR UPDATE` 串行化），并把 `path.replace()` 前移到校验之后、建用户之前。

---

## 三、中优先级问题（P2）

| # | 问题 | 证据 | 影响 |
| --- | --- | --- | --- |
| P2-1 | RBAC 种子不完整 | `app/auth/rbac.py:46-54` | `support` / `operator` 无任何权限，登录后台即 403，角色形同虚设；`superadmin` 缺 `provider:manage` / `model:publish` / `refund:execute`；`admin` 可用 `admin:access` 创建优惠券（等价发钱）却无 `ledger:adjust` 制约 |
| P2-2 | 明文密钥查看无频控 / 无 MFA | `app/keys/router.py:114-125`、`keys/service.py:476-517` | 仅校验登录口令，会话被盗后可无限次尝试口令并批量导出历史 Key；建议加失败计数 + 已开启 TOTP 时强制二次验证 |
| P2-3 | 读请求触发写放大 | `auth/deps.py:65-71`（每次请求改 `last_seen_at` / `idle_expires_at`）、`keys/service.py:264`（每次网关调用改 `last_used_at`） | 同一会话的多标签页并发 GET 会对同一行加锁；同一 API Key 高并发时 `api_keys` 行成为热点。建议改为「按 5 分钟窗口节流写入」或异步合并 |
| P2-4 | 限流与并发闸为进程内状态 | `app/gateway/limit.py`、`main.py:100-101` | 多 worker / 多副本时实际阈值 = 配置值 × 进程数；`_hits` 字典永不回收，长跑进程内存单调增长。建议迁移到 Redis（已有依赖） |
| P2-5 | Stripe 签名头重复 `v1` 只取最后一个 | `app/payments/signatures.py:14-21` | 官方密钥轮换期会同时下发两个 `v1`，取最后一个导致验签随机失败。应遍历全部 `v1` 做常量时间比较 |
| P2-6 | 重复邮箱注册竞态返回 500 | `app/db/session.py:28-30` 原样抛 `IntegrityError`，`core/errors.py` 无处理器 | 并发注册同一邮箱时，后到者得到 `500 INTERNAL` 而非 `409 EMAIL_TAKEN`。建议在异常处理器中映射唯一冲突 |
| P2-7 | 邮件令牌可用性设计欠佳 | `auth/service.py:274-279`（重置链接不含 token，正文要求手工复制）、`resend_verification` 返回 `already_verified`（`auth/service.py:107-108`） | 可用性差；且该响应可用于批量探测「某邮箱是否已注册并激活」 |
| P2-8 | 备份文件为全库明文、位于仓库目录 | `ops/platform.py:36`、`533-560` | 备份含口令哈希、上游凭证密文、全部客户数据，落盘在代码仓库同级 `backups/`；仅 `admin:access` 可创建/删除，无下载入口（这点是对的），但缺少加密、异地与保留策略；误提交风险高（建议同时加入 `.gitignore` 校验） |

---

## 四、低优先级问题（P3）

1. **TOTP 未防重放**：`auth/service.py:379`、`553` 使用 `verify(valid_window=1)` 但未记录已用时间步，同一 6 位码在 ±30 秒窗口内可重复使用。
2. **时段计费标签取值不精确**：`billing/pricing.py:299-306` 取 `schedule_rules["rules"]` 的**第一条** `label`，而非实际命中的那条规则，仅影响排障可读性。
3. **占位与清理**：`apps/web/scripts/_*.py` 有 12 个一次性迁移/扫描脚本留在仓库，建议移入 `scripts/` 或删除，避免误用。

---

## 五、自动化检查结果

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 语法编译 | `python -m compileall apps/api/app scripts` | 通过 |
| ruff | `ruff check app`（pyproject 规则集 E/F/I/UP/B） | **All checks passed** |
| mypy | `mypy app`（`disallow_untyped_defs`、`strict_equality`） | **Success: no issues found in 90 source files** |
| pytest | `pytest`（105 用例） | **104 passed, 1 skipped**（PG 并发用例因当前角色非表属主而跳过） |
| 前端 lint / vitest / build | 未执行 | 环境无 `node_modules`，未安装依赖；CI 中可覆盖 |

说明：为本次审查新建了隔离虚拟环境 `.venv-review/`（不污染项目依赖），审查结束后可删除。

---

## 六、做得好的部分（建议保留）

- **令牌与凭证处理**：会话/验证/重置令牌仅存 SHA-256 摘要（`auth/tokens.py`）；API Key 明文使用 AES-256-GCM 加密且带版本头、拒绝开发默认密钥（`keys/crypto.py`）；上游凭证同样以 Fernet 派生密钥加密（`auth/crypto.py`）。
- **SSRF 防护**：`security/ssrf.py` 逐跳解析、IP 钉扎 + SNI 保持、元数据地址与私有网段拦截、自建端点白名单，属于较完整的实现。
- **账本设计**：只追加流水 + 幂等键唯一约束 + `FOR UPDATE` 行锁 + 余额/预扣/冻结的非负与可用性检查（`db/models/billing.py:96-99`），方向常量表清晰。
- **职责分离**：退款「申请 / 复核 / 执行」三方互斥（`payments/service.py:451, 475`），审计哈希链带单行锁（`admin/audit.py:53`）。
- **错误信封与 i18n**：业务码稳定、文案集中、前端按语言映射，且明确「不把后端中文 message 直接呈现」。

---

## 七、修复路线建议

**第一批（上线阻断，预计 1-2 天）**
1. P0-2 补 `cron_jobs` + 分批释放；P0-3 异常路径结清预扣；P0-4 统一错误码常量 → 三者合并修复，构成「资金不再泄漏」的闭环。
2. P0-5 IP 透传三处联动修复，并补多层代理单测。
3. P1-1 修正测试替身优先级，让 CI 恢复绿灯。

**第二批（上线前必做，预计 2-3 天）**
4. P0-1 支付网关落地，或显式关闭 `stripe` / `usdt` 下单入口并在启动期校验。
5. P1-2 / P1-3 / P1-4 / P1-5 前端与边界加固。
6. P1-6 / P1-7 并发正确性修复并补并发用例。

**第三批（上线后一个迭代）**
7. P2-1 RBAC 重新梳理；P2-2 密钥查看加频控与 MFA；P2-3 / P2-4 热点行与限流改造；P2-8 备份加密与保留策略。

---

## 八、结论

代码的「骨架」质量高于同类项目平均水平：分层、错误处理、凭证加密、审计与职责分离都有明确设计痕迹。真正的问题集中在**运行期闭环**——预扣的释放、支付查单、定时任务调度、代理链 IP —— 这些恰恰是静态代码看着正确、但一旦上线就以「余额冻结 / 充值不入账 / 注册被限流」形式暴露的部分。

建议按上述三批推进；在 P0 全部关闭前，不应对外开放充值入口与生产流量。

---

## 九、修复与复验（2026-11-09 续）

本节记录对上述问题的实际处置。所有改动均已通过 `ruff` / `mypy` / `pytest`。

| 编号 | 问题 | 处置 | 复验 |
| --- | --- | --- | --- |
| P0-1 | 支付渠道内存占位、查单必然失配 | `payments/gateways.py` 重写：Stripe 走 Checkout Sessions 创建 + 查单，USDT 走服务商 HTTP 查单；订单保存 `provider_ref` 与 `provider_snapshot`（新增迁移 0018）；未配置渠道在 `_assert_channel` 直接拒绝下单 | 支付用例通过 |
| P0-2 | cron 从未被调度 | `worker.py` 补 `cron_jobs`：释放预扣每 15 秒、关单每 5 分钟、兜底结清每 10 分钟、审计链每日 | 启动 `WorkerSettings` 可见 4 类周期任务 |
| P0-3 | 上游异常不释放预扣 | `gateway/service.py` 新增 `_settle_unsuccessful`，`complete` / `embeddings` / `stream` 三条路径的异常分支统一按 0 token 结清；`ledger.release_expired` 支持分批 | 计费与网关用例通过 |
| P0-4 | 余额不足错误码分裂 | `core/errors.py` 导出常量 `BALANCE_INSUFFICIENT`，`ledger` / `billing` 全部引用常量，保留旧码仅用于文案兼容 | 争议结算用例通过 |
| P0-5 | 真实 IP 全链路丢失 | nginx 所有 location 写 XFF；uvicorn 加 `--proxy-headers --forwarded-allow-ips`；BFF 透传 XFF；新增 `core/request_ip.py` 统一解析（优先 `request.client`，兜底取 XFF 最右一跳） | 注册限流恢复按 IP 计数 |
| P1-1 | 测试替身被全局 client 覆盖 | 网关与 providers 两处都改为 **transport 优先**；`providers/router._service` 修正「把 AsyncClient 当 transport」的误传 | 原 6 个失败用例全部恢复 |
| P1-2 | 只透传最后一个 Cookie | `proxy.ts` 改为一次性 `join("; ")` | — |
| P1-3 | 缺 CSP / HSTS | `next.config.ts` 统一注入 CSP、HSTS、X-Frame-Options 等 | — |
| P1-4 | 请求体限制可绕过 | 中间件改为累计字节数；**关键点**：FastAPI 会把 body 读取阶段的任意异常兜底成 400，因此不再抛信号，改为「截断输入 + 丢弃应用响应 + 自回 413」 | 新增 chunked 超限断言 |
| P1-5 | `X-Request-Id` 由客户端决定 | 仍接受合法格式但由服务端兜底生成，usage 主键改为服务端生成 | — |
| P1-6 | 优惠券超发 | 改为条件更新 `UPDATE ... WHERE used_count < max_uses`，按受影响行数判定，并捕获唯一冲突映射 409 | — |
| P1-7 | 初始化超管竞态 | 建号前对角色表加锁串行化，并补充 `IntegrityError` → 409 映射 | — |
| P2-3 | 进程内限流不准 | 新增 `RedisRateLimiter` / `RedisSlots`（固定窗口 + TTL），Redis 故障自动降级到进程内实现，按启动期可用性装配 | 网关用例通过 |
| P2-4 | 热点行写放大 | 会话 `last_seen_at`、API Key `last_used_at`、凭证 `last_used_at` 统一压到 60 秒窗口写一次 | — |
| P2-7 | TOTP 可重放 | `users.totp_last_step` 水位线（迁移 0019），同一时间步只接受一次 | — |
| 新增 | **执行面断链**：模型上架只写自家库，LiteLLM `model_list` 为空 | 见 `docs/ARCHITECTURE_REVIEW.md` 第二节：新增 `providers/litellm_registry.py`，上架/下架/换凭证/部署状态变更时同步 LiteLLM；新增对账 cron 与 `registry_synced_at` / `registry_error`（迁移 0020） | 新增同步用例断言 payload |

仍未处理：P2-8 备份加密、P2-1 RBAC 细粒度复核、P3 级别的可观测性增强，见架构评估「待办」。`X-Request-Id` 目前仍接受客户端值，若后续要彻底防伪造，可改为「客户端值仅作为日志关联字段，usage 主键一律服务端生成」。

---

## 十、第三批：可观测性与运维闭环（2026-11-09 晚）

上一批把「资金与鉴权的不变量」补住了，这一批解决「出了问题能不能第一时间发现」和
「出问题后能不能自证」。全部改动通过 `ruff` / `mypy` / `pytest`（113 passed / 1 skipped）。

| 方向 | 落地内容 | 位置 |
| --- | --- | --- |
| 指标 | 零依赖指标注册表（counter / histogram / gauge），暴露 `/metrics`（text 0.0.4）；可选 `METRICS_TOKEN` 鉴权；DB 故障时仍返回进程指标 | `core/metrics.py`、`api/routes.py` |
| HTTP 观测 | 中间件记录请求量、状态码、耗时直方图、in-flight；路径中的 UUID / 数字折叠为 `{id}`，避免标签基数爆炸 | `core/middleware.py` |
| 业务指标 | 预扣未结清笔数与金额、`usage` 长期 pending 数、LiteLLM 注册失败数；15 秒进程内缓存，避免抓取打爆 DB | `ops/metrics.py` |
| 错误分布 | `AppError` 与 404/405 统一计入 `forge_api_errors_total{code}` | `core/errors.py` |
| 告警 | 7 条 Prometheus 规则：实例失联、5xx 比例、上游持续失败、注册失败、预扣堆积、pending 堆积、非流式 P95 | `deploy/prometheus/alerts.yml` |
| 账本对账 | `GET /api/admin/ledger/reconcile`：按流水重算 balance / frozen、按预扣表重算 held；`apply=true` 修复并写审计链，需 `ledger:adjust` | `ops/ledger_audit.py`、`ops/router.py` |
| 备份加密 | `BACKUP_ENCRYPTION_KEY`（Fernet）开启后，导出即加密并删除明文；列表可识别 `.enc`；配套 `scripts/decrypt_backup.py` | `ops/platform.py`、`scripts/` |
| PG 膨胀 | worker 新增 `purge_litellm_logs`：按保留期分批删除 LiteLLM 日志表；LiteLLM 侧同时关闭消息正文落库 | `worker.py`、`deploy/litellm/config.yaml` |
| 多进程 | uvicorn `--workers`（默认 2）与 `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` 联动，compose 按 2 workers 下调连接池 | `apps/api/Dockerfile`、compose |
| Redis 隔离 | 限流/并发闸改用 `REDIS_RATE_LIMIT_URL`（db1），与 arq 队列（db0）分库 | `core/config.py`、`main.py` |
| 边缘限流 | nginx 按 IP 分桶：登录类 5r/s、`/v1` 30r/s + 并发上限，先挡一层再进应用 | `deploy/nginx/nginx.conf` |
| 链路追踪 | 网关转发时把 `x-request-id` 传给 LiteLLM，可一路查到 Provider | `gateway/service.py` |
| 依赖审计 | CI 增加 `pnpm audit --prod --audit-level high` | `.github/workflows/ci.yml` |

### 这一批里值得记住的两个坑

1. **`/metrics` 不能依赖 `get_db`**：数据库挂了才更需要指标。端点直接从 `app.state.sessionmaker`
   取会话并吞掉业务指标异常，保证「DB 不可用但进程活着」这个状态可被抓取到。
2. **备份加密要先校验密钥再导出**：否则密钥配错时会先在磁盘留下一个明文 dump，加密失败的
   异常反而成了次要问题。

### 仍未处理（按优先级）

1. **RBAC 细粒度复核**（P2-1）：`admin:access` 仍是粗粒度闸门，财务与客服角色边界需按业务再切；
2. **Key 缓存 Redis 化**：多 worker 下 `MemoryKeyCache` 各存一份，吊销最长 30 秒才全量生效（有界，但不够快）；
3. **PgBouncer / LiteLLM 库拆分**：当前 2 workers 的连接数仍在安全区，规模再上一个量级才需要；
4. **流式备份加密**：现为整文件 Fernet，GB 级库应换 `age`/`gpg`；
5. **跨实例 cron 锁**：worker 保持单副本即可；多副本时 cron 会重复触发（任务幂等，但会抢锁）。
