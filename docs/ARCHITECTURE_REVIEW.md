# 架构与选型评估

> 范围：`apps/api`（FastAPI）、`apps/web`（Next.js BFF）、`deploy/*`（nginx / compose / LiteLLM）、
> 以及与 PostgreSQL、Redis、arq 的搭配方式。结论基于仓库当前代码与部署文件，不做外部基准测试。

## 一、总体判断

整体是「**控制面自建 + 执行面委托 LiteLLM**」的两段式架构：

```
浏览器 ──nginx──> Next BFF (/api/*)  ──┐
   └──────────> FastAPI (/v1/*) ─────────┴──> LiteLLM ──> 上游 Provider
                     │
                     └── PostgreSQL（业务 + 账本） / Redis（缓存 + 限流 + 队列）
```

这个划分本身是合理的：计费、额度、审计、凭证加密这些「只有自己知道」的逻辑留在 FastAPI，
多厂商协议适配、重试、fallback 交给 LiteLLM，避免重复造轮子。

问题不在划分，而在**两个状态源之间没有同步通道**——这也是本次改动最大的一块。

## 二、执行面：LiteLLM 与自家模型目录

### 2.1 已修复的断链

原实现里 `/v1` 的模型名会被替换成 `model_catalog.upstream_name` 后转发给 LiteLLM，
但 LiteLLM 的 `deploy/litellm/config.yaml` 是 `model_list: []`，且没有任何代码把模型推过去。
后果是「后台显示已上架、真实调用 400 model not found」，而这一步在测试里恰好被 mock 掩盖。

现在的做法（`providers/litellm_registry.py`）：

- 上架 / 下架 / 部署启停 / 凭证轮换 → 调用 LiteLLM Admin API（`/model/new`、`/model/delete`）；
- 幂等键用 `model_info.id = model_deployments.id`，重复注册即覆盖；
- `store_model_in_db: true`，否则 LiteLLM 重启后动态模型全丢；
- 同步失败**不阻断**上架事务，写 `model_deployments.registry_error`，由 arq 每 10 分钟对账补偿；
- 对账任务还会清理「已下架但 LiteLLM 仍在接单」的残留。

### 2.2 仍需接受的双状态源成本

即便有同步，LiteLLM 的 model 表与 `model_deployments` 仍是两份状态。以下场景会漂移，必须靠对账收敛：

| 场景 | 表现 | 兜底 |
| --- | --- | --- |
| 上架时 LiteLLM 不可达 | 后台已上架，调用 404 | 对账任务重推（10 分钟内） |
| 凭证轮换后推送失败 | 调用 401 | `_push_provider` 失败写 error，对账重试 |
| 人工在 LiteLLM 侧改动 | 两边不一致 | 对账只补不删（除 disabled 的），人工改动会被覆盖 |

**建议**：把「注册成功」做成上架的强校验（可选开关）。当前选择「尽力而为 + 对账」是为了不让 LiteLLM 抖动阻塞运营操作，
代价是存在最长 10 分钟的不一致窗口。若业务不能接受，应改为「注册失败即上架失败」并返回明确错误码。

### 2.3 模型命名约定

- 对外（用户请求）：`model_catalog.public_name`
- 转发给 LiteLLM：`upstream_name`（网关在 `prepare` 阶段替换）
- LiteLLM 注册的 `model_name` 同样是 `upstream_name`

三者一致是当前设计的前提。**新增厂商适配时不要改这条约定**，否则会出现「计费按 A 模型、实际调用 B 模型」。
若未来同 `upstream_name` 需要多供应商负载均衡，LiteLLM 支持同名多 deployment，`model_info.id` 仍唯一，可直接扩展。

## 三、存储层

### 3.1 PostgreSQL：单实例双库

业务库与 LiteLLM 库（`litellm` database）在同一个 PG 实例上，靠不同 database 隔离。风险：

- **资源竞争**：LiteLLM 的 `spend_logs`、`request_logs` 增长快，会与账本查询抢 IO 和连接；
- **连接数**：`main.py` 的业务池是 `pool_size=5, max_overflow=10`，按进程计。若 API 起多 worker，
  总连接数 = 15 × worker 数，再叠加 worker 进程与 LiteLLM 自己的池，容易打满 `max_connections`。

**建议**：
1. LiteLLM 的日志表加保留策略（定期 `DELETE ... WHERE startTime < now() - interval '30 days'`），
   或直接关闭 `request_logs` 落库，只留 spend 聚合；
2. API 起多 worker 时同步下调 `pool_size`，或在前面加 PgBouncer（transaction 模式）；
3. 中期把 LiteLLM 库拆到独立实例，故障域也就分开了。

### 3.2 Redis：一个实例承担三种职责

当前 db0 同时用于：Key 缓存（`MemoryKeyCache` 的 Redis 版）、限流/并发闸、arq 队列。三者淘汰策略冲突：

- 缓存希望 `allkeys-lru`；
- 队列**绝不能**被淘汰，否则任务丢失。

**建议**：物理分实例，或至少 `SELECT` 不同 db（缓存 db1、队列 db0），队列所在实例禁用淘汰策略
（`maxmemory-policy noeviction`）。当前代码里限流键有 `forge:rl:` / `forge:slot:` 前缀，迁移成本低。

### 3.3 账本

只追加流水 + 幂等键唯一约束 + 行锁，是本项目做得最扎实的部分。唯一要盯的是**余额快照表与流水的一致性**：
`account_balances` 是聚合结果，一旦某次事务只写了流水没更新快照，就需要重算工具。
建议补一个「按流水重算快照」的运维接口（只读比对 + 差异修复），对账时会救命。

## 四、运行时与部署

### 4.1 uvicorn 单进程

`Dockerfile` 的启动命令没有 `--workers`，即单进程。async I/O 场景下单进程能撑住相当并发，但：

- CPU 密集（JSON 编解码、加密解密、账本计算）会串行；
- 一个进程崩溃 = 全部请求中断；
- 限流若退回进程内实现（Redis 故障），单进程反而是「准确」的，多进程则不准确。

**建议**：生产起 `--workers 2~4`，并把 `pool_size` 相应下调；同时确认 `RedisRateLimiter` 已生效（当前按 `redis` 可用性自动装配）。

### 4.2 arq 与 cron

补上 `cron_jobs` 后，资金闭环才真正成立。但 arq 的 cron 是**每个 worker 实例各自触发**：

- `release_expired_holds`、`close_expired_payments`、`reconcile_litellm_registry` 都是幂等的，重复执行不会错账；
- 但会造成无谓的锁竞争与日志噪音。

**建议**：worker 保持单副本；若要多副本，给 cron 任务加 Redis 分布式锁（`SET NX EX`）。

### 4.3 nginx

- `/v1/` 已 `proxy_buffering off`（SSE 必需），本次把 `proxy_read_timeout` 从 180s 提到 600s：
  长上下文生成超过 180 秒会被中途掐断，表现为「输出到一半停了」；
- `proxy_set_header` 是「本层定义即不继承」，`location /` 之前缺 `X-Real-IP`，已补；
- 建议加 `limit_req_zone` 做边缘限流，挡住明显的刷接口流量，减轻应用层压力。

### 4.4 镜像与前端

- 前端 `output: standalone` + 多阶段构建，镜像体积合理；
- BFF（`/api/[...path]`）是「Node 再转 FastAPI」的一跳。对 JSON 接口影响很小，
  但**不要**把 `/v1` 的流式请求接到 BFF 上——Node 侧需要 `duplex: "half"` 且容易缓冲，
  当前 nginx 把 `/v1/` 直连 API 是正确选择。

## 五、安全边界

| 边界 | 现状 | 评价 |
| --- | --- | --- |
| 客户端 IP | nginx 写 XFF → uvicorn `--proxy-headers` 改写 `scope["client"]` → 应用优先用它 | 链路完整；`--forwarded-allow-ips` 默认 `*`，依赖「api 端口不对外」这一前提，compose 里确实没映射端口，可接受但要写进部署检查清单 |
| 上游凭证 | Fernet 派生密钥加密存库，响应只回 hint | 好；但 LiteLLM 侧会再存一份明文 `api_key`（由其自身加密策略决定），等于多一处副本 |
| 备份 | `pg_dump` 产出明文文件 | **待办**：加 `age`/GPG 加密 + 保留期 + 异地存储 |
| 会话 | HttpOnly + SameSite + 滑动空闲 + 绝对过期 | 好；已加 60 秒写节流 |
| 请求体 | 累计字节数 + 413 | 已修；注意 FastAPI 会吞 body 读取异常，实现上不能靠抛异常 |

关于「凭证在 LiteLLM 再存一份」：这是选择「保留 LiteLLM」的固有代价。若合规要求单一密钥存储，
应改为 API 侧直连上游（届时 LiteLLM 仅作可选旁路）。当前可做的最小缓解是限制 LiteLLM 容器网络出口与 DB 访问权限。

## 六、可观测性

已有：structlog JSON 日志、`X-Request-Id` 贯穿、审计哈希链、`/healthz` `/readyz` 分离。

缺：
1. **指标**：没有 Prometheus 端点。至少应暴露 QPS、P95 延迟、402/429/5xx 比例、预扣未结清数量、
   LiteLLM 注册失败数（`registry_error` 非空计数）。
2. **链路追踪**：跨 API → LiteLLM → 上游没有 trace id 传递。LiteLLM 支持透传 `x-request-id`，
   建议在 `_headers()` 里带上，出问题能一条链路查到上游。
3. **告警**：`usage` 长期 `pending`、`balance_holds` 堆积、`registry_error` 增长，都应触发告警而不是只写日志。

## 七、依赖与版本

- 后端用 `uv` + `pyproject`，锁文件固定，CI 有 `pip-audit`；
- 前端 `pnpm` + lockfile，但 CI 未跑 `pnpm audit`，建议补；
- `next 16 + react 19` 属于较新组合，standalone 构建已验证；注意 Next 的 middleware（`proxy.ts`）
  运行在 Edge runtime，不能使用 Node API——当前实现只做 cookie 转发与 fetch，符合约束。

## 八、优化清单

**已落地（本次）**

- 模型上架/下架/换凭证/部署状态 → LiteLLM 同步 + 对账 cron；
- 限流与并发闸 Redis 化（故障自动降级）；
- 热点行写入压到 60 秒窗口（会话、API Key、凭证）；
- nginx 流式超时 600s、补齐 `X-Real-IP`；
- 请求体超限真正生效（含 chunked）。

**建议排期**

1. LiteLLM 日志表保留策略 / 关闭 request_logs 落库（防 PG 膨胀）；
2. Redis 按用途分 db 或分实例，队列实例 `noeviction`；
3. uvicorn `--workers` 与连接池联动，必要时上 PgBouncer；
4. 备份加密 + 保留期；
5. Prometheus 指标 + 关键告警（预扣堆积、注册失败、5xx 比例）；
6. 「按流水重算余额快照」的运维工具；
7. 前端 `pnpm audit` 进 CI。

## 九、一句话总结

架构方向是对的，短板集中在**跨组件的状态一致性**与**运行期可观测性**：
前者靠「同步 + 对账」补齐，后者目前几乎是空白。资金与鉴权相关的不变量已经守住了，
下一步应该把「出了问题能不能第一时间发现」补上。
