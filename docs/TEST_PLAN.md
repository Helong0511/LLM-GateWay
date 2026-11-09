# 测试计划

用例编号沿用需求 §16.0。这里只登记已经写进仓库、并且要在当前环境执行的用例。没有执行的用例不标通过。

## 阶段 2 已编写

| 编号 | 位置 | 内容 |
| --- | --- | --- |
| TC-DEP-010 的探针部分 | `tests/api/test_health.py` | `/healthz` 信封与请求 ID；`/readyz` 在探针失败时返回 503 和检查明细 |
| TC-SEC-010 的脱敏部分 | `tests/api/test_redaction.py`、`tests/api/test_errors.py` | 密码、sk-、私钥、邮箱打码；500 响应不带内部字符串 |
| TC-PAY-120 | `tests/api/test_settings.py` | 生产配置拒绝 mock 支付 |
| TC-DEP-020 | `tests/api/test_settings.py` | 生产配置拒绝演示模型 |
| TC-FE-001 | `tests/web/bff.test.ts` | 已执行：2 passed。BFF 地址拼接与路径穿越 |

身份表是否映射到模型，由 `tests/api/test_schema.py` 检查。它不连接数据库。

## 阶段 3 到阶段 6 已执行

2026-10-28 在仓库根目录执行 `apps/api/.venv/Scripts/python.exe -m pytest -q`，结果 `55 passed`。

| 编号 | 位置 | 内容 |
| --- | --- | --- |
| TC-AUTH-*、TC-RBAC-* | `tests/api/test_auth.py` | 注册、登录、会话、二次验证、角色拒绝 |
| TC-KEY-* | `tests/api/test_keys.py` | 密钥、用量隔离、零余额 |
| TC-GW-* | `tests/api/test_gateway.py` | Mock 上游转发、限流、槽位、SSRF |
| TC-BILL-* | `tests/api/test_billing.py` | 账本不变量、过期预扣、网关扣费与失败释放 |
| TC-PAY-* | `tests/api/test_payments.py` | 充值幂等、USDT 三重校验、Stripe 查单、退款三人、对账、汇率 |
| TC-CONC-* | `tests/api/test_billing.py` | 对真实 `forge` 库并发同一幂等键只入账一次 |

## 尚未执行

TC-ADMIN 覆盖概览、用户冻结、审计链、全部订单、退款列表、只读账本和调用记录：未登录 401，普通用户 403。财务可以看退款列表但不能看账本。分配角色写入哈希链，篡改明细后校验失败。充值目录缺档时补 10、50、100，重复读取不新增。工单、发票、公告、优惠券入账、配置白名单、备份拒绝无效地址、任务探活和内容审计哈希另有服务测试：未完成订单不能开发票，优惠券重复兑换不重复入账，配置响应不含连接串。分页测试覆盖同时间戳 25 条翻页：两页 id 无交集、并集等于 total，不再用硬截断 50 条当全量。压测与 ZAP 还没做。真实上游和真实链上转账没有跑。

真实上游和真实链上转账使用 `@pytest.mark.live`，默认不跑。没有凭证时不得记为通过。

覆盖率门槛（billing/payments/security/rbac ≥ 90%，整体 ≥ 75%）从这些模块存在时开始强制。当前这四个领域包还没有业务代码，不计算空目录覆盖率。
