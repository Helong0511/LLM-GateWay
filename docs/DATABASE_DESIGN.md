# 数据库设计（草图）

主键统一 UUID。时间戳为 `timestamptz`。金额为 `NUMERIC`，禁止 `float`。账本只追加。余额不放在 `users` 表。

阶段 2 迁移 `20261028_0001` 只创建身份相关表，并写入七个系统角色。其余表在对应阶段迁移，字段以本节为准。

## 身份与权限（阶段 2 已迁移）

`users`：id，email，email_normalized（唯一，小写去空格），password_hash（Argon2id），status（`pending_verification/active/frozen/deleted`），failed_login_count，locked_until，totp_enabled，totp_secret_encrypted，terms_version，terms_accepted_at，privacy_version，privacy_accepted_at，register_ip，register_user_agent，created_at，updated_at，deleted_at。

`user_profiles`：user_id 主键外键，display_name，timezone，locale，company_name，notification_prefs（jsonb）。阶段 3 迁移。

`roles`：id，code 唯一，name，description，is_system。种子：user、support、finance、operator、model_ops、admin、superadmin。

`permissions`：id，code 唯一（`资源:操作`），description。权限点由代码常量维护，阶段 3 写入。

`role_permissions`：role_id + permission_id。需求实体清单没有这张连接表，没有它角色无法绑定权限点，因此作为实施增补。

`user_roles`：user_id + role_id，granted_by，granted_at。

`sessions`：id，user_id，token_hash（SHA-256 十六进制，唯一），created_at，last_seen_at，absolute_expires_at，idle_expires_at，revoked_at，created_ip，last_seen_ip，user_agent。不存会话明文。

`login_devices`：id，user_id，device_label，first_ip，last_ip，user_agent，first_seen_at，last_seen_at。

`email_verification_tokens`、`password_reset_tokens`：id，user_id，token_hash 唯一，expires_at，attempt_count，consumed_at，created_at。

`email_change_tokens`：同上，并增加 new_email、new_email_normalized。

## 供应商与模型

`providers`：id，name，slug 唯一，provider_type，base_url，protocol，credential_ref，enabled，timeout_ms，health_status，priority，weight，max_concurrency，rpm_limit，tpm_limit，allow_private_network（默认 false），created_at，updated_at。

`provider_credentials`：id，provider_id，litellm_secret_ref，key_fingerprint，masked_preview（前 4 后 4），status，last_used_at，rotated_at。无明文列。

`model_catalog`：id，slug 唯一，display_name，public_model_name 唯一，upstream_model_name，provider_id，context_window，max_output_tokens，supports_stream，supports_tools，supports_vision，supports_embeddings，supports_image。未知能力保持空，界面显示「未确认」，不填猜测值。enabled，created_at，updated_at。

`model_deployments`：id，model_id，provider_id，endpoint_model_name，weight，priority，enabled，health_status，timeout_ms。

`routing_policies`：id，model_id，strategy，fallback_model_ids（jsonb），retry_policy（jsonb），enabled。

`model_sync_jobs`：id，provider_id，status，started_at，finished_at，summary（jsonb），requested_by。

## 价格、用量与账本

`pricing_versions`：id，model_id，version，currency，effective_from，effective_to，created_by。调价新增版本，不改历史。

`model_prices`：id，pricing_version_id，meter（input_token / output_token / cached_input_token / image 等），unit_price，cost_price，min_billable_units。均为 numeric。

`exchange_rates`：id，base_currency，quote_currency，rate，source，captured_at。

`api_keys`：id，user_id，name，key_prefix，key_hash 唯一，status，expires_at，rpm_limit，tpm_limit，max_concurrency，budget_limit，budget_spent，ip_allowlist（jsonb），last_used_at，created_at，revoked_at。

`api_key_model_permissions`：api_key_id + model_id。

`usage_records`：按 `started_at` 月分区。request_id 唯一，user_id，api_key_id，model_id，deployment_id，started_at，first_token_at，ended_at，input_tokens，output_tokens，cached_tokens，provider_cost，user_charge，currency，pricing_version_id，unit_price_snapshot（jsonb），http_status，error_class，is_stream，settlement_status（pending / settled / released / disputed），usage_source（reported / estimated），finish_reason。默认不存提示词和回复。

`usage_settlements`：id，usage_record_id，status，hold_id，ledger_entry_id，settled_at。

`account_balances`：user_id + currency 主键，balance，held，frozen，updated_at。检查约束三者均大于等于 0。可用余额 = balance - held - frozen，不单独存储。

`account_ledger`：只追加。id，user_id，entry_type（需求附录 B），amount（正数 numeric），currency，idempotency_key 全局唯一，balance_before，balance_after，reference_type，reference_id，reason，created_at，created_by。禁止更新和删除，纠错用反向流水。

`balance_holds`：id，user_id，amount，currency，idempotency_key 唯一，status（held / committed / released），expires_at，request_id，created_at，closed_at。每笔预扣只能走向 commit 或 release 之一。

`idempotency_records`：实施增补。key 唯一，request_hash，status_code，response_body，created_at，expires_at。同键不同载荷返回 409。

## 支付

`recharge_products`：id，name，amount，currency，bonus_amount，enabled，sort_order。

`payment_orders`：id，order_no 唯一，user_id，product_id，channel，amount，currency，crypto_amount，crypto_currency，network，pay_address，status，locked_rate，rate_source，locked_at，expires_at，provider_ref，tx_hash，confirmations，actual_amount，created_at，updated_at。USDT 状态机：pending → confirming → completed | expired | underpaid | overpaid | closed，之后可以到 refunded。

`payment_events`：id，order_id，source，payload_redacted（jsonb），signature_ok，created_at。原文脱敏后可重放。

`refund_orders`：id，order_id，amount，status（requested / reviewed / executed / rejected），requested_by，reviewed_by，executed_by，destination_address，tx_hash，reason，created_at。USDT 退款只能退回链上原地址，发起人与执行人不得相同。

`crypto_deposit_intents`：id，order_id，address，network，tail_amount，tail_status（reserved / used / released），expires_at。

`sanctioned_address_blocks`：id，address，network，source，reason，created_at。

## 商业化与运营

`subscription_plans`、`user_subscriptions`、`usage_packages`：套餐与资源包。未启用时界面显示「未启用」，表结构按需求一次建齐。

`coupons`、`coupon_redemptions`：优惠券与核销。

`invoices`：id，user_id，order_id，title，tax_no，amount，status，created_at。

`quotas`、`rate_limit_policies`：配额与限流策略。财务硬限制仍以 PostgreSQL 预扣为准。

`system_settings`：key 主键，value（jsonb），updated_at，updated_by。

`audit_logs`：id，actor_id，action，object_type，object_id，before_summary，after_summary，result，ip，request_id，prev_hash，content_hash，created_at。不记录密码、验证码、Cookie、完整 API Key、上游密钥和私钥。

`outbox_events`：id，event_type，payload，status，created_at，published_at。

`notifications`：id，user_id，category，title，body，read_at，created_at。安全类通知不可关闭。

`announcements`：id，slug 唯一，title，body，published_at。

`tickets`、`ticket_messages`：分类含账单、技术、退款、链上转账异常、其他。状态 open / pending / resolved / closed。

`content_audit_records`：id，user_id，model_id，direction（input/output），category，summary_hash，created_at。默认不存原文。

`webhook_subscriptions`、`webhook_deliveries`：可选。签名、重试和投递记录。

`task_failures`：实施增补，供后台查看死信。id，task_name，payload_id，error_class，attempts，created_at。

## 保留

| 数据 | 热保留 | 之后 |
| --- | --- | --- |
| usage_records | 6 个月 | 归档 12 个月后删除，合规要求更长时以合规为准 |
| 调用内容 | 默认不存；启用后不超过 30 天 | 到期删除 |
| account_ledger | 永久 | 只归档 |
| payment_orders / payment_events | 至少 5 年 | 只归档 |
| audit_logs | 至少 3 年 | 只归档，哈希链校验 |
| sessions 与令牌 | 过期后 30 天 / 7 天 | 删除 |

手工对账 SQL 放在 `sql/`。表结构变更只走 Alembic。
