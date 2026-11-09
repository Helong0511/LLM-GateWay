-- ============================================================
-- Forge API · 测试环境完整初始化 SQL
-- 版本: 2026-11-02
-- 数据库: PostgreSQL 15+
-- 字符集: UTF-8（本文件必须以 UTF-8 无 BOM 保存与导入）
-- 说明: 完整表结构 + 中文注释 + 高并发索引 + 基础种子 + 测试模拟数据。独立执行，不依赖 forge_prod.sql
-- ============================================================
-- 客户端字符集显式指定为 UTF-8，禁止依赖系统默认
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
-- 如需新建数据库，先执行（template0 避免编码依赖）：
-- CREATE DATABASE forge_test WITH ENCODING 'UTF8' TEMPLATE template0;
-- \c forge_test;
-- ============================================================
-- 第一部分：扩展
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- UUID 生成函数
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- 加密函数
-- ============================================================
-- 第二部分：表结构（按外键依赖拓扑排序）
-- ============================================================
-- ========== 通知与工单 ==========
CREATE TABLE announcements (
	id UUID NOT NULL,
	slug VARCHAR(80) NOT NULL,
	title VARCHAR(160) NOT NULL,
	body TEXT NOT NULL,
	published BOOLEAN NOT NULL DEFAULT FALSE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_announcements_slug UNIQUE (slug)
);
COMMENT ON TABLE announcements IS '平台公告';
COMMENT ON COLUMN announcements.id IS '主键（UUID）';
COMMENT ON COLUMN announcements.slug IS '标识（URL 友好，唯一）';
COMMENT ON COLUMN announcements.title IS '标题';
COMMENT ON COLUMN announcements.body IS '正文';
COMMENT ON COLUMN announcements.published IS '是否发布';
COMMENT ON COLUMN announcements.created_at IS '创建时间（UTC）';
-- ========== 审计与合规 ==========
CREATE TABLE audit_chain_lock (id SERIAL NOT NULL, PRIMARY KEY (id));
COMMENT ON TABLE audit_chain_lock IS '审计哈希链锁：单行表，串行化链尾写入';
COMMENT ON COLUMN audit_chain_lock.id IS '固定为 1（单行锁表）';
CREATE TABLE content_safety_settings (
	id SERIAL NOT NULL,
	enabled BOOLEAN NOT NULL DEFAULT FALSE,
	PRIMARY KEY (id)
);
COMMENT ON TABLE content_safety_settings IS '内容安全开关（单行配置）';
COMMENT ON COLUMN content_safety_settings.id IS '主键（UUID）';
COMMENT ON COLUMN content_safety_settings.enabled IS '是否启用内容安全审计';
-- ========== 模型与上游 ==========
CREATE TABLE endpoint_allowlist (
	id UUID NOT NULL,
	host VARCHAR(255) NOT NULL,
	approved BOOLEAN NOT NULL DEFAULT FALSE,
	note VARCHAR(256) NOT NULL DEFAULT '',
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_endpoint_allowlist_host UNIQUE (host)
);
COMMENT ON TABLE endpoint_allowlist IS '上游端点白名单：防止 SSRF 到非授权主机';
COMMENT ON COLUMN endpoint_allowlist.id IS '主键（UUID）';
COMMENT ON COLUMN endpoint_allowlist.host IS '允许的上游主机名';
COMMENT ON COLUMN endpoint_allowlist.approved IS '是否已审批';
COMMENT ON COLUMN endpoint_allowlist.note IS '备注';
COMMENT ON COLUMN endpoint_allowlist.created_at IS '创建时间（UTC）';
-- ========== 支付与充值 ==========
CREATE TABLE exchange_rates (
	id UUID NOT NULL,
	base_currency VARCHAR(8) NOT NULL,
	quote_currency VARCHAR(8) NOT NULL,
	rate NUMERIC(24, 8) NOT NULL,
	source VARCHAR(64) NOT NULL,
	captured_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
);
COMMENT ON TABLE exchange_rates IS '汇率快照：充值/结算时的币种换算依据';
COMMENT ON COLUMN exchange_rates.id IS '主键（UUID）';
COMMENT ON COLUMN exchange_rates.base_currency IS '基准币种';
COMMENT ON COLUMN exchange_rates.quote_currency IS '报价币种';
COMMENT ON COLUMN exchange_rates.rate IS '汇率（1 base = rate quote）';
COMMENT ON COLUMN exchange_rates.source IS '来源（manual/api）';
COMMENT ON COLUMN exchange_rates.captured_at IS '采集时间';
-- ========== 后台任务 ==========
CREATE TABLE job_runs (
	id UUID NOT NULL,
	name VARCHAR(64) NOT NULL,
	status VARCHAR(16) NOT NULL,
	detail VARCHAR(256) NOT NULL DEFAULT '',
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_job_runs_status CHECK (status IN ('succeeded', 'failed'))
);
COMMENT ON TABLE job_runs IS '后台任务执行记录';
COMMENT ON COLUMN job_runs.id IS '主键（UUID）';
COMMENT ON COLUMN job_runs.name IS '任务名';
COMMENT ON COLUMN job_runs.status IS '状态：running/success/failed';
COMMENT ON COLUMN job_runs.detail IS '执行详情';
COMMENT ON COLUMN job_runs.created_at IS '创建时间（UTC）';
-- ========== 账户与认证 ==========
CREATE TABLE permissions (
	id UUID NOT NULL,
	code VARCHAR(128) NOT NULL,
	description TEXT NOT NULL DEFAULT '',
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (code)
);
COMMENT ON TABLE permissions IS '权限点定义：后台操作的最小授权单元';
COMMENT ON COLUMN permissions.id IS '主键（UUID）';
COMMENT ON COLUMN permissions.code IS '权限代码（如 refund:execute）';
COMMENT ON COLUMN permissions.description IS '权限说明';
COMMENT ON COLUMN permissions.created_at IS '创建时间（UTC）';
-- ========== 模型与上游 ==========
CREATE TABLE providers (
	id UUID NOT NULL,
	name VARCHAR(128) NOT NULL,
	kind VARCHAR(32) NOT NULL,
	base_url TEXT NOT NULL,
	protocol VARCHAR(32) NOT NULL DEFAULT 'openai',
	status VARCHAR(16) NOT NULL DEFAULT 'active',
	timeout_seconds INTEGER NOT NULL DEFAULT 60,
	priority INTEGER NOT NULL DEFAULT 100,
	weight INTEGER NOT NULL DEFAULT 1,
	max_concurrency INTEGER,
	rpm_limit INTEGER,
	tpm_limit INTEGER,
	last_error VARCHAR(256),
	last_latency_ms INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_providers_kind CHECK (
		kind IN (
			'openai',
			'anthropic',
			'cloud',
			'self_hosted',
			'ollama',
			'compatible'
		)
	),
	CONSTRAINT ck_providers_status CHECK (status IN ('active', 'disabled', 'deleted'))
);
COMMENT ON TABLE providers IS '上游供应商：协议、限速、并发、健康状态';
COMMENT ON COLUMN providers.id IS '主键（UUID）';
COMMENT ON COLUMN providers.name IS '供应商标识（小写，如 deepseek/openrouter）';
COMMENT ON COLUMN providers.kind IS '类型：official/compatible/ollama 等';
COMMENT ON COLUMN providers.base_url IS '上游 API 基础地址';
COMMENT ON COLUMN providers.protocol IS '协议方言：openai/anthropic 等';
COMMENT ON COLUMN providers.status IS '状态：active/disabled';
COMMENT ON COLUMN providers.timeout_seconds IS '请求超时（秒）';
COMMENT ON COLUMN providers.priority IS '优先级（越小越优先）';
COMMENT ON COLUMN providers.weight IS '负载均衡权重';
COMMENT ON COLUMN providers.max_concurrency IS '最大并发数';
COMMENT ON COLUMN providers.rpm_limit IS '每分钟请求数上限';
COMMENT ON COLUMN providers.tpm_limit IS '每分钟 token 数上限';
COMMENT ON COLUMN providers.last_error IS '最近一次错误信息';
COMMENT ON COLUMN providers.last_latency_ms IS '最近一次调用耗时（毫秒）';
COMMENT ON COLUMN providers.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN providers.updated_at IS '更新时间（UTC）';
-- ========== 支付与充值 ==========
CREATE TABLE recharge_products (
	id UUID NOT NULL,
	name VARCHAR(128) NOT NULL,
	amount NUMERIC(24, 8) NOT NULL,
	currency VARCHAR(8) NOT NULL,
	bonus_amount NUMERIC(24, 8) NOT NULL DEFAULT 0,
	enabled BOOLEAN NOT NULL DEFAULT TRUE,
	sort_order INTEGER NOT NULL DEFAULT 0,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	allowed_models TEXT NOT NULL DEFAULT '[]',
	PRIMARY KEY (id),
	CONSTRAINT ck_recharge_products_amount CHECK (amount > 0),
	CONSTRAINT ck_recharge_products_bonus CHECK (bonus_amount >= 0)
);
COMMENT ON TABLE recharge_products IS '充值套餐：面额、赠送金额、排序';
COMMENT ON COLUMN recharge_products.id IS '主键（UUID）';
COMMENT ON COLUMN recharge_products.name IS '套餐名称';
COMMENT ON COLUMN recharge_products.amount IS '金额';
COMMENT ON COLUMN recharge_products.currency IS '币种（ISO 4217，如 USD/CNY）';
COMMENT ON COLUMN recharge_products.bonus_amount IS '赠送金额';
COMMENT ON COLUMN recharge_products.enabled IS '是否上架';
COMMENT ON COLUMN recharge_products.sort_order IS '展示排序（越小越前）';
COMMENT ON COLUMN recharge_products.deleted_at IS '软删除时间，NULL 表示未删除';
COMMENT ON COLUMN recharge_products.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN recharge_products.allowed_models IS '套餐默认可用模型（JSON 数组，空数组=不限）';
-- ========== 账户与认证 ==========
CREATE TABLE roles (
	id UUID NOT NULL,
	code VARCHAR(64) NOT NULL,
	name VARCHAR(128) NOT NULL,
	description TEXT NOT NULL DEFAULT '',
	is_system BOOLEAN NOT NULL DEFAULT TRUE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (code)
);
COMMENT ON TABLE roles IS '角色定义：user/support/finance/operator/model_ops/admin/superadmin';
COMMENT ON COLUMN roles.id IS '主键（UUID）';
COMMENT ON COLUMN roles.code IS '角色代码（程序引用，如 superadmin）';
COMMENT ON COLUMN roles.name IS '角色显示名';
COMMENT ON COLUMN roles.is_system IS '是否系统内置角色（禁止删除）';
COMMENT ON COLUMN roles.created_at IS '创建时间（UTC）';
-- ========== 审计与合规 ==========
CREATE TABLE sanctioned_address_blocks (
	id UUID NOT NULL,
	address VARCHAR(128) NOT NULL,
	network VARCHAR(16) NOT NULL,
	source VARCHAR(64) NOT NULL,
	reason VARCHAR(256) NOT NULL DEFAULT '',
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_sanctioned_address_network UNIQUE (address, network)
);
COMMENT ON TABLE sanctioned_address_blocks IS '制裁地址黑名单：加密货币收款风控';
COMMENT ON COLUMN sanctioned_address_blocks.id IS '主键（UUID）';
COMMENT ON COLUMN sanctioned_address_blocks.address IS '黑名单地址';
COMMENT ON COLUMN sanctioned_address_blocks.network IS '区块链网络';
COMMENT ON COLUMN sanctioned_address_blocks.source IS '名单来源';
COMMENT ON COLUMN sanctioned_address_blocks.reason IS '封禁原因';
COMMENT ON COLUMN sanctioned_address_blocks.created_at IS '创建时间（UTC）';
-- ========== 账户与认证 ==========
CREATE TABLE users (
	id UUID NOT NULL,
	email VARCHAR(320) NOT NULL,
	email_normalized VARCHAR(320) NOT NULL,
	password_hash TEXT NOT NULL,
	status VARCHAR(32) NOT NULL DEFAULT 'pending_verification',
	failed_login_count INTEGER NOT NULL DEFAULT 0,
	locked_until TIMESTAMP WITH TIME ZONE,
	totp_enabled BOOLEAN NOT NULL DEFAULT FALSE,
	totp_secret_encrypted TEXT,
	terms_version VARCHAR(64),
	terms_accepted_at TIMESTAMP WITH TIME ZONE,
	privacy_version VARCHAR(64),
	privacy_accepted_at TIMESTAMP WITH TIME ZONE,
	register_ip VARCHAR(64),
	register_user_agent TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	allowed_models TEXT NOT NULL DEFAULT '[]',
	PRIMARY KEY (id),
	CONSTRAINT ck_users_status CHECK (
		status IN (
			'pending_verification',
			'active',
			'frozen',
			'deleted'
		)
	),
	UNIQUE (email_normalized)
);
COMMENT ON TABLE users IS '用户主表：账号、密码哈希、状态、登录安全与合规字段';
COMMENT ON COLUMN users.id IS '主键（UUID）';
COMMENT ON COLUMN users.email IS '登录邮箱（原始输入）';
COMMENT ON COLUMN users.email_normalized IS '规范化邮箱（小写，唯一索引）';
COMMENT ON COLUMN users.password_hash IS '密码哈希（Argon2id）';
COMMENT ON COLUMN users.status IS '账号状态：active/frozen/deleted';
COMMENT ON COLUMN users.failed_login_count IS '连续登录失败次数（锁定计数）';
COMMENT ON COLUMN users.locked_until IS '锁定截止时间，NULL 表示未锁定';
COMMENT ON COLUMN users.totp_enabled IS '是否已启用 TOTP 二次验证';
COMMENT ON COLUMN users.totp_secret_encrypted IS 'TOTP 密钥（加密存储）';
COMMENT ON COLUMN users.terms_version IS '已同意的服务条款版本';
COMMENT ON COLUMN users.terms_accepted_at IS '服务条款同意时间';
COMMENT ON COLUMN users.privacy_version IS '已同意的隐私政策版本';
COMMENT ON COLUMN users.privacy_accepted_at IS '隐私政策同意时间';
COMMENT ON COLUMN users.register_ip IS '注册时 IP';
COMMENT ON COLUMN users.register_user_agent IS '注册时 User-Agent';
COMMENT ON COLUMN users.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN users.updated_at IS '更新时间（UTC）';
COMMENT ON COLUMN users.deleted_at IS '软删除时间，NULL 表示未删除';
COMMENT ON COLUMN users.allowed_models IS '账号级可用模型（JSON 数组，空数组=未显式配置，回退到套餐范围）';
-- ========== 计费与账本 ==========
CREATE TABLE account_balances (
	user_id UUID NOT NULL,
	currency VARCHAR(8) NOT NULL,
	balance NUMERIC(24, 8) NOT NULL DEFAULT 0,
	held NUMERIC(24, 8) NOT NULL DEFAULT 0,
	frozen NUMERIC(24, 8) NOT NULL DEFAULT 0,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (user_id, currency),
	CONSTRAINT ck_account_balances_balance CHECK (balance >= 0),
	CONSTRAINT ck_account_balances_held CHECK (held >= 0),
	CONSTRAINT ck_account_balances_frozen CHECK (frozen >= 0),
	CONSTRAINT ck_account_balances_available CHECK (balance >= held + frozen),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);
COMMENT ON TABLE account_balances IS '账户余额表：可用余额、冻结中预扣、风控冻结';
COMMENT ON COLUMN account_balances.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN account_balances.currency IS '币种（ISO 4217，如 USD/CNY）';
COMMENT ON COLUMN account_balances.balance IS '可用余额';
COMMENT ON COLUMN account_balances.held IS '预扣冻结中金额（请求处理中）';
COMMENT ON COLUMN account_balances.frozen IS '风控冻结金额（不可用）';
COMMENT ON COLUMN account_balances.updated_at IS '更新时间（UTC）';
CREATE TABLE account_ledger (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	entry_type VARCHAR(32) NOT NULL,
	direction VARCHAR(1) NOT NULL,
	amount NUMERIC(24, 8) NOT NULL,
	currency VARCHAR(8) NOT NULL,
	idempotency_key VARCHAR(160) NOT NULL,
	balance_before NUMERIC(24, 8) NOT NULL,
	balance_after NUMERIC(24, 8) NOT NULL,
	reference_type VARCHAR(32),
	reference_id VARCHAR(64),
	reason VARCHAR(256) NOT NULL DEFAULT '',
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_by UUID,
	PRIMARY KEY (id),
	CONSTRAINT uq_account_ledger_idempotency UNIQUE (idempotency_key),
	CONSTRAINT ck_account_ledger_amount CHECK (amount > 0),
	CONSTRAINT ck_account_ledger_direction CHECK (direction IN ('C', 'D', 'N')),
	CONSTRAINT ck_account_ledger_balance CHECK (
		balance_before >= 0
		AND balance_after >= 0
	),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE
	SET NULL
);
CREATE INDEX IF NOT EXISTS ix_account_ledger_user_id ON account_ledger (user_id);
CREATE INDEX IF NOT EXISTS ix_account_ledger_user_created ON account_ledger (user_id, created_at);
COMMENT ON TABLE account_ledger IS '账户账本（只追加）：所有余额变动的唯一事实来源';
COMMENT ON COLUMN account_ledger.id IS '主键（UUID）';
COMMENT ON COLUMN account_ledger.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN account_ledger.entry_type IS '条目类型：recharge/consume/refund/adjust/bonus 等';
COMMENT ON COLUMN account_ledger.direction IS '方向：credit（入账）/debit（出账）';
COMMENT ON COLUMN account_ledger.amount IS '金额';
COMMENT ON COLUMN account_ledger.currency IS '币种（ISO 4217，如 USD/CNY）';
COMMENT ON COLUMN account_ledger.idempotency_key IS '幂等键（唯一，防重复入账）';
COMMENT ON COLUMN account_ledger.balance_before IS '变动前余额';
COMMENT ON COLUMN account_ledger.balance_after IS '变动后余额';
COMMENT ON COLUMN account_ledger.reference_type IS '关联单据类型（order/usage/refund 等）';
COMMENT ON COLUMN account_ledger.reference_id IS '关联单据 ID';
COMMENT ON COLUMN account_ledger.reason IS '变动原因备注';
COMMENT ON COLUMN account_ledger.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN account_ledger.created_by IS '创建人用户 ID';
COMMENT ON INDEX ix_account_ledger_user_id IS '按用户查询账本流水';
COMMENT ON INDEX ix_account_ledger_user_created IS '高并发：用户按时间倒序翻页账单流水';
-- ========== API 密钥 ==========
CREATE TABLE api_keys (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	name VARCHAR(128) NOT NULL,
	key_prefix VARCHAR(24) NOT NULL,
	key_hash VARCHAR(64) NOT NULL,
	key_ciphertext TEXT,
	key_enc_version INTEGER NOT NULL DEFAULT 0,
	status VARCHAR(16) NOT NULL DEFAULT 'active',
	expires_at TIMESTAMP WITH TIME ZONE,
	rpm_limit INTEGER,
	tpm_limit INTEGER,
	max_concurrency INTEGER,
	budget_limit NUMERIC(24, 8),
	budget_spent NUMERIC(24, 8) NOT NULL DEFAULT 0,
	allowed_models TEXT NOT NULL DEFAULT '[]',
	ip_allowlist TEXT NOT NULL DEFAULT '[]',
	last_used_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	revoked_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_api_keys_status CHECK (
		status IN ('active', 'disabled', 'revoked', 'expired')
	),
	CONSTRAINT ck_api_keys_key_hash_len CHECK (char_length(key_hash) = 64),
	CONSTRAINT uq_api_keys_key_hash UNIQUE (key_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_api_keys_user_id ON api_keys (user_id);
COMMENT ON TABLE api_keys IS 'API 密钥：哈希存储，含限速/并发/预算/模型白名单';
COMMENT ON COLUMN api_keys.id IS '主键（UUID）';
COMMENT ON COLUMN api_keys.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN api_keys.name IS '密钥备注名';
COMMENT ON COLUMN api_keys.key_prefix IS '密钥前缀（展示用，如 sk-abcd）';
COMMENT ON COLUMN api_keys.key_hash IS '密钥哈希（SHA-256，用于网关 lookup，不存明文）';
COMMENT ON COLUMN api_keys.key_ciphertext IS '密钥 AES-256-GCM 密文（格式 v1|iv|tag|body），NULL=历史无加密（仅 digest）';
COMMENT ON COLUMN api_keys.key_enc_version IS '加密算法版本：0=无，1=AES-256-GCM';
COMMENT ON COLUMN api_keys.status IS '状态：active/revoked';
COMMENT ON COLUMN api_keys.expires_at IS '过期时间（UTC）';
COMMENT ON COLUMN api_keys.rpm_limit IS '每分钟请求数上限';
COMMENT ON COLUMN api_keys.tpm_limit IS '每分钟 token 数上限';
COMMENT ON COLUMN api_keys.max_concurrency IS '最大并发请求数';
COMMENT ON COLUMN api_keys.budget_limit IS '预算上限（USD），NULL 表示不限';
COMMENT ON COLUMN api_keys.budget_spent IS '已消耗预算';
COMMENT ON COLUMN api_keys.allowed_models IS '已废弃：模型范围改由账号（users.allowed_models）决定，此列固定为空数组';
COMMENT ON COLUMN api_keys.ip_allowlist IS 'IP 白名单（JSON 数组，空=不限）';
COMMENT ON COLUMN api_keys.last_used_at IS '最近使用时间';
COMMENT ON COLUMN api_keys.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN api_keys.revoked_at IS '吊销时间';
COMMENT ON INDEX ix_api_keys_user_id IS '按用户查询密钥列表';
-- ========== 审计与合规 ==========
CREATE TABLE audit_events (
	id UUID NOT NULL,
	seq INTEGER NOT NULL,
	actor_id UUID,
	action VARCHAR(64) NOT NULL,
	target_type VARCHAR(64) NOT NULL,
	target_id VARCHAR(64) NOT NULL,
	detail VARCHAR(256) NOT NULL DEFAULT '',
	prev_hash VARCHAR(64) NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	recorded_at VARCHAR(32) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_audit_events_seq UNIQUE (seq),
	CONSTRAINT uq_audit_events_content_hash UNIQUE (content_hash),
	FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE
	SET NULL
);
COMMENT ON TABLE audit_events IS '审计事件（哈希链）：后台敏感操作的不可篡改流水';
COMMENT ON COLUMN audit_events.id IS '主键（UUID）';
COMMENT ON COLUMN audit_events.seq IS '链内序号（严格递增）';
COMMENT ON COLUMN audit_events.actor_id IS '操作人用户 ID';
COMMENT ON COLUMN audit_events.action IS '操作类型';
COMMENT ON COLUMN audit_events.target_type IS '目标对象类型';
COMMENT ON COLUMN audit_events.target_id IS '目标对象 ID';
COMMENT ON COLUMN audit_events.detail IS '操作详情（JSON，脱敏）';
COMMENT ON COLUMN audit_events.prev_hash IS '前一条事件哈希（链式防篡改）';
COMMENT ON COLUMN audit_events.content_hash IS '本条内容哈希';
COMMENT ON COLUMN audit_events.recorded_at IS '记录时间';
COMMENT ON COLUMN audit_events.created_at IS '创建时间（UTC）';
CREATE TABLE content_audit_records (
	id UUID NOT NULL,
	user_id UUID,
	model_name VARCHAR(128) NOT NULL,
	category VARCHAR(32) NOT NULL,
	summary_hash VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE
	SET NULL
);
COMMENT ON TABLE content_audit_records IS '内容审计记录：命中安全策略的请求摘要';
COMMENT ON COLUMN content_audit_records.id IS '主键（UUID）';
COMMENT ON COLUMN content_audit_records.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN content_audit_records.model_name IS '调用模型名';
COMMENT ON COLUMN content_audit_records.category IS '命中类别';
COMMENT ON COLUMN content_audit_records.summary_hash IS '内容摘要哈希（不存原文）';
COMMENT ON COLUMN content_audit_records.created_at IS '创建时间（UTC）';
-- ========== 支付与充值 ==========
CREATE TABLE coupons (
	id UUID NOT NULL,
	code VARCHAR(32) NOT NULL,
	bonus_amount NUMERIC(24, 8) NOT NULL,
	currency VARCHAR(8) NOT NULL,
	max_uses INTEGER NOT NULL,
	used_count INTEGER NOT NULL DEFAULT 0,
	enabled BOOLEAN NOT NULL DEFAULT TRUE,
	expires_at TIMESTAMP WITH TIME ZONE,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_by UUID,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_coupons_code UNIQUE (code),
	CONSTRAINT ck_coupons_bonus CHECK (bonus_amount > 0),
	CONSTRAINT ck_coupons_uses CHECK (
		max_uses >= 1
		AND used_count >= 0
		AND used_count <= max_uses
	),
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE
	SET NULL
);
COMMENT ON TABLE coupons IS '优惠券：固定面额赠送，限使用次数';
COMMENT ON COLUMN coupons.id IS '主键（UUID）';
COMMENT ON COLUMN coupons.code IS '优惠码（唯一）';
COMMENT ON COLUMN coupons.bonus_amount IS '赠送金额';
COMMENT ON COLUMN coupons.currency IS '币种（ISO 4217，如 USD/CNY）';
COMMENT ON COLUMN coupons.max_uses IS '最大使用次数';
COMMENT ON COLUMN coupons.used_count IS '已使用次数';
COMMENT ON COLUMN coupons.enabled IS '是否启用';
COMMENT ON COLUMN coupons.expires_at IS '过期时间（UTC）';
COMMENT ON COLUMN coupons.deleted_at IS '软删除时间，NULL 表示未删除';
COMMENT ON COLUMN coupons.created_by IS '创建人用户 ID';
COMMENT ON COLUMN coupons.created_at IS '创建时间（UTC）';
-- ========== 账户与认证 ==========
CREATE TABLE email_change_tokens (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	new_email VARCHAR(320) NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	attempt_count INTEGER NOT NULL DEFAULT 0,
	consumed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_email_change_token_hash_len CHECK (char_length(token_hash) = 64),
	CONSTRAINT uq_email_change_token_hash UNIQUE (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_email_change_tokens_user_id ON email_change_tokens (user_id);
COMMENT ON TABLE email_change_tokens IS '换绑邮箱令牌（哈希存储，一次性）';
COMMENT ON COLUMN email_change_tokens.id IS '主键（UUID）';
COMMENT ON COLUMN email_change_tokens.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN email_change_tokens.new_email IS '待换绑的新邮箱';
COMMENT ON COLUMN email_change_tokens.token_hash IS '令牌哈希（不存明文）';
COMMENT ON COLUMN email_change_tokens.expires_at IS '过期时间（UTC）';
COMMENT ON COLUMN email_change_tokens.attempt_count IS '已尝试验证次数（防爆破）';
COMMENT ON COLUMN email_change_tokens.consumed_at IS '核销时间，NULL 表示未使用';
COMMENT ON COLUMN email_change_tokens.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_email_change_tokens_user_id IS '按用户查询换绑令牌';
CREATE TABLE email_verification_tokens (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	attempt_count INTEGER NOT NULL DEFAULT 0,
	consumed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_email_verification_token_hash_len CHECK (char_length(token_hash) = 64),
	CONSTRAINT uq_email_verification_token_hash UNIQUE (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_email_verification_tokens_user_id ON email_verification_tokens (user_id);
COMMENT ON TABLE email_verification_tokens IS '邮箱验证令牌（哈希存储，一次性）';
COMMENT ON COLUMN email_verification_tokens.id IS '主键（UUID）';
COMMENT ON COLUMN email_verification_tokens.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN email_verification_tokens.token_hash IS '令牌哈希（不存明文）';
COMMENT ON COLUMN email_verification_tokens.expires_at IS '过期时间（UTC）';
COMMENT ON COLUMN email_verification_tokens.attempt_count IS '已尝试验证次数（防爆破）';
COMMENT ON COLUMN email_verification_tokens.consumed_at IS '核销时间，NULL 表示未使用';
COMMENT ON COLUMN email_verification_tokens.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_email_verification_tokens_user_id IS '按用户查询验证令牌';
CREATE TABLE idempotency_records (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	idempotency_key VARCHAR(80) NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	status_code INTEGER NOT NULL,
	response_body TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_idempotency_user_key UNIQUE (user_id, idempotency_key),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
COMMENT ON TABLE idempotency_records IS '通用幂等记录：防止重复提交造成重复处理';
COMMENT ON COLUMN idempotency_records.id IS '主键（UUID）';
COMMENT ON COLUMN idempotency_records.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN idempotency_records.idempotency_key IS '幂等键';
COMMENT ON COLUMN idempotency_records.request_hash IS '请求体哈希';
COMMENT ON COLUMN idempotency_records.status_code IS '已响应的 HTTP 状态码';
COMMENT ON COLUMN idempotency_records.response_body IS '已缓存的响应体';
COMMENT ON COLUMN idempotency_records.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN idempotency_records.expires_at IS '过期时间（UTC）';
-- ========== 支付与充值 ==========
CREATE TABLE invoice_requests (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	order_no VARCHAR(40) NOT NULL,
	title VARCHAR(160) NOT NULL,
	tax_no VARCHAR(64) NOT NULL DEFAULT '',
	amount NUMERIC(24, 8) NOT NULL,
	currency VARCHAR(8) NOT NULL,
	status VARCHAR(16) NOT NULL DEFAULT 'requested',
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_invoice_requests_order UNIQUE (order_no),
	CONSTRAINT ck_invoice_requests_status CHECK (status IN ('requested', 'issued', 'rejected')),
	CONSTRAINT ck_invoice_requests_amount CHECK (amount > 0),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
COMMENT ON TABLE invoice_requests IS '发票申请记录';
COMMENT ON COLUMN invoice_requests.id IS '主键（UUID）';
COMMENT ON COLUMN invoice_requests.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN invoice_requests.order_no IS '关联订单号';
COMMENT ON COLUMN invoice_requests.title IS '发票抬头';
COMMENT ON COLUMN invoice_requests.tax_no IS '税号';
COMMENT ON COLUMN invoice_requests.amount IS '金额';
COMMENT ON COLUMN invoice_requests.currency IS '币种（ISO 4217，如 USD/CNY）';
COMMENT ON COLUMN invoice_requests.status IS '状态：pending/issued/rejected';
COMMENT ON COLUMN invoice_requests.created_at IS '创建时间（UTC）';
-- ========== 账户与认证 ==========
CREATE TABLE login_devices (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	user_agent TEXT NOT NULL DEFAULT '',
	ip VARCHAR(64) NOT NULL DEFAULT '',
	last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_login_devices_user_id ON login_devices (user_id);
COMMENT ON TABLE login_devices IS '登录设备记录：最近登录的 UA 与 IP';
COMMENT ON COLUMN login_devices.id IS '主键（UUID）';
COMMENT ON COLUMN login_devices.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN login_devices.ip IS '登录 IP';
COMMENT ON COLUMN login_devices.last_seen_at IS '最近活跃时间';
COMMENT ON COLUMN login_devices.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_login_devices_user_id IS '按用户查询登录设备';
CREATE TABLE mfa_challenges (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	attempt_count INTEGER NOT NULL DEFAULT 0,
	consumed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_mfa_challenge_token_hash_len CHECK (char_length(token_hash) = 64),
	CONSTRAINT uq_mfa_challenge_token_hash UNIQUE (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_mfa_challenges_user_id ON mfa_challenges (user_id);
COMMENT ON TABLE mfa_challenges IS 'MFA 二次验证挑战（TOTP 流程临时凭证）';
COMMENT ON COLUMN mfa_challenges.id IS '主键（UUID）';
COMMENT ON COLUMN mfa_challenges.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN mfa_challenges.token_hash IS '令牌哈希（不存明文）';
COMMENT ON COLUMN mfa_challenges.expires_at IS '过期时间（UTC）';
COMMENT ON COLUMN mfa_challenges.attempt_count IS '已尝试验证次数（防爆破）';
COMMENT ON COLUMN mfa_challenges.consumed_at IS '核销时间，NULL 表示未使用';
COMMENT ON COLUMN mfa_challenges.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_mfa_challenges_user_id IS '按用户查询 MFA 挑战';
-- ========== 模型与上游 ==========
CREATE TABLE model_catalog (
	id UUID NOT NULL,
	provider_id UUID NOT NULL,
	public_name VARCHAR(128) NOT NULL,
	display_name VARCHAR(128) NOT NULL,
	upstream_name VARCHAR(128) NOT NULL,
	status VARCHAR(16) NOT NULL DEFAULT 'pending',
	supports_stream BOOLEAN,
	supports_tools BOOLEAN,
	supports_vision BOOLEAN,
	supports_embeddings BOOLEAN,
	supports_images BOOLEAN,
	context_window INTEGER,
	max_output INTEGER,
	upstream_input_price NUMERIC(24, 8),
	upstream_output_price NUMERIC(24, 8),
	upstream_schedule_rules JSONB,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_model_catalog_status CHECK (status IN ('pending', 'published', 'disabled')),
	CONSTRAINT uq_model_catalog_provider_upstream UNIQUE (provider_id, upstream_name),
	FOREIGN KEY(provider_id) REFERENCES providers (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_model_catalog_provider_id ON model_catalog (provider_id);
COMMENT ON TABLE model_catalog IS '模型目录：对外模型定义、能力位、上游建议价与时段规则';
COMMENT ON COLUMN model_catalog.id IS '主键（UUID）';
COMMENT ON COLUMN model_catalog.provider_id IS '供应商 ID → providers.id';
COMMENT ON COLUMN model_catalog.public_name IS '对外模型名（API 调用时使用）';
COMMENT ON COLUMN model_catalog.display_name IS '展示名';
COMMENT ON COLUMN model_catalog.upstream_name IS '上游真实模型 ID';
COMMENT ON COLUMN model_catalog.status IS '状态：pending/published/disabled';
COMMENT ON COLUMN model_catalog.supports_stream IS '是否支持流式输出';
COMMENT ON COLUMN model_catalog.supports_tools IS '是否支持工具调用';
COMMENT ON COLUMN model_catalog.supports_vision IS '是否支持图像输入';
COMMENT ON COLUMN model_catalog.supports_embeddings IS '是否支持向量嵌入';
COMMENT ON COLUMN model_catalog.supports_images IS '是否支持图像生成';
COMMENT ON COLUMN model_catalog.context_window IS '上下文窗口（token 数）';
COMMENT ON COLUMN model_catalog.max_output IS '最大输出 token 数';
COMMENT ON COLUMN model_catalog.upstream_input_price IS '上游建议输入价（USD/token）';
COMMENT ON COLUMN model_catalog.upstream_output_price IS '上游建议输出价（USD/token）';
COMMENT ON COLUMN model_catalog.upstream_schedule_rules IS '上游时段定价规则原文（JSONB）';
COMMENT ON COLUMN model_catalog.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_model_catalog_provider_id IS '按供应商查询模型';
CREATE TABLE model_sync_jobs (
	id UUID NOT NULL,
	provider_id UUID NOT NULL,
	status VARCHAR(16) NOT NULL,
	discovered_count INTEGER NOT NULL DEFAULT 0,
	error VARCHAR(256),
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	finished_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_model_sync_jobs_status CHECK (status IN ('running', 'succeeded', 'failed')),
	FOREIGN KEY(provider_id) REFERENCES providers (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_model_sync_jobs_provider_id ON model_sync_jobs (provider_id);
COMMENT ON TABLE model_sync_jobs IS '模型同步任务：从上游拉取模型列表的执行记录';
COMMENT ON COLUMN model_sync_jobs.id IS '主键（UUID）';
COMMENT ON COLUMN model_sync_jobs.provider_id IS '供应商 ID → providers.id';
COMMENT ON COLUMN model_sync_jobs.status IS '状态';
COMMENT ON COLUMN model_sync_jobs.discovered_count IS '本次发现的模型数量';
COMMENT ON COLUMN model_sync_jobs.error IS '错误信息';
COMMENT ON COLUMN model_sync_jobs.started_at IS '开始时间';
COMMENT ON COLUMN model_sync_jobs.finished_at IS '结束时间';
COMMENT ON INDEX ix_model_sync_jobs_provider_id IS '按供应商查询同步任务';
CREATE TABLE model_test_runs (
	id UUID NOT NULL,
	provider_id UUID NOT NULL,
	mode VARCHAR(32) NOT NULL,
	ok BOOLEAN NOT NULL,
	http_status INTEGER,
	latency_ms INTEGER,
	usage_present BOOLEAN NOT NULL DEFAULT FALSE,
	error VARCHAR(256),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(provider_id) REFERENCES providers (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_model_test_runs_provider_id ON model_test_runs (provider_id);
COMMENT ON TABLE model_test_runs IS '模型可用性测试记录';
COMMENT ON COLUMN model_test_runs.id IS '主键（UUID）';
COMMENT ON COLUMN model_test_runs.provider_id IS '供应商 ID → providers.id';
COMMENT ON COLUMN model_test_runs.mode IS '测试模式：chat/embedding 等';
COMMENT ON COLUMN model_test_runs.ok IS '是否成功';
COMMENT ON COLUMN model_test_runs.http_status IS 'HTTP 状态码';
COMMENT ON COLUMN model_test_runs.latency_ms IS '耗时（毫秒）';
COMMENT ON COLUMN model_test_runs.usage_present IS '上游是否返回 usage';
COMMENT ON COLUMN model_test_runs.error IS '错误信息';
COMMENT ON COLUMN model_test_runs.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_model_test_runs_provider_id IS '按供应商查询测试记录';
-- ========== 通知与工单 ==========
CREATE TABLE notification_preferences (
	user_id UUID NOT NULL,
	balance_alerts_enabled BOOLEAN NOT NULL DEFAULT TRUE,
	warn_high NUMERIC(24, 8) NOT NULL DEFAULT 10,
	warn_low NUMERIC(24, 8) NOT NULL DEFAULT 2,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (user_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
COMMENT ON TABLE notification_preferences IS '通知偏好：余额预警阈值等';
COMMENT ON COLUMN notification_preferences.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN notification_preferences.balance_alerts_enabled IS '是否开启余额预警';
COMMENT ON COLUMN notification_preferences.warn_high IS '高阈值';
COMMENT ON COLUMN notification_preferences.warn_low IS '低阈值';
COMMENT ON COLUMN notification_preferences.updated_at IS '更新时间（UTC）';
CREATE TABLE notifications (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	kind VARCHAR(32) NOT NULL,
	title VARCHAR(160) NOT NULL,
	body TEXT NOT NULL DEFAULT '',
	related_id UUID,
	dedupe_key VARCHAR(160) NOT NULL,
	read_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_notifications_kind CHECK (kind IN ('security', 'key_expiry', 'balance')),
	CONSTRAINT uq_notifications_user_dedupe UNIQUE (user_id, dedupe_key),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_notifications_user_unread ON notifications (user_id, created_at)
WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id);
COMMENT ON TABLE notifications IS '站内通知';
COMMENT ON COLUMN notifications.id IS '主键（UUID）';
COMMENT ON COLUMN notifications.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN notifications.kind IS '通知类型';
COMMENT ON COLUMN notifications.title IS '标题';
COMMENT ON COLUMN notifications.body IS '正文';
COMMENT ON COLUMN notifications.related_id IS '关联对象 ID';
COMMENT ON COLUMN notifications.dedupe_key IS '去重键（防止重复通知）';
COMMENT ON COLUMN notifications.read_at IS '阅读时间，NULL 表示未读';
COMMENT ON COLUMN notifications.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_notifications_user_unread IS '高并发：未读通知拉取（部分索引，只含未读）';
COMMENT ON INDEX ix_notifications_user_id IS '按用户查询通知';
-- ========== 账户与认证 ==========
CREATE TABLE password_reset_tokens (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	attempt_count INTEGER NOT NULL DEFAULT 0,
	consumed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_password_reset_token_hash_len CHECK (char_length(token_hash) = 64),
	CONSTRAINT uq_password_reset_token_hash UNIQUE (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id ON password_reset_tokens (user_id);
COMMENT ON TABLE password_reset_tokens IS '密码重置令牌（哈希存储，一次性）';
COMMENT ON COLUMN password_reset_tokens.id IS '主键（UUID）';
COMMENT ON COLUMN password_reset_tokens.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN password_reset_tokens.token_hash IS '令牌哈希（不存明文）';
COMMENT ON COLUMN password_reset_tokens.expires_at IS '过期时间（UTC）';
COMMENT ON COLUMN password_reset_tokens.attempt_count IS '已尝试验证次数（防爆破）';
COMMENT ON COLUMN password_reset_tokens.consumed_at IS '核销时间，NULL 表示未使用';
COMMENT ON COLUMN password_reset_tokens.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_password_reset_tokens_user_id IS '按用户查询重置令牌';
-- ========== 支付与充值 ==========
CREATE TABLE payment_orders (
	id UUID NOT NULL,
	order_no VARCHAR(40) NOT NULL,
	user_id UUID NOT NULL,
	product_id UUID,
	channel VARCHAR(16) NOT NULL,
	amount NUMERIC(24, 8) NOT NULL,
	currency VARCHAR(8) NOT NULL,
	bonus_amount NUMERIC(24, 8) NOT NULL DEFAULT 0,
	credited_amount NUMERIC(24, 8),
	crypto_amount NUMERIC(24, 8),
	crypto_currency VARCHAR(8),
	network VARCHAR(16),
	pay_address VARCHAR(128),
	payer_address VARCHAR(128),
	status VARCHAR(16) NOT NULL DEFAULT 'pending',
	locked_rate NUMERIC(24, 8),
	rate_source VARCHAR(64),
	locked_at TIMESTAMP WITH TIME ZONE,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	provider_ref VARCHAR(128),
	tx_hash VARCHAR(128),
	confirmations INTEGER NOT NULL DEFAULT 0,
	actual_amount NUMERIC(24, 8),
	risk_status VARCHAR(16) NOT NULL DEFAULT 'clear',
	reconcile_status VARCHAR(16) NOT NULL DEFAULT 'unchecked',
	idempotency_key VARCHAR(80) NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	paid_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_payment_orders_order_no UNIQUE (order_no),
	CONSTRAINT uq_payment_orders_user_idempotency UNIQUE (user_id, idempotency_key),
	CONSTRAINT ck_payment_orders_status CHECK (
		status IN (
			'pending',
			'confirming',
			'completed',
			'expired',
			'underpaid',
			'overpaid',
			'closed',
			'refunded'
		)
	),
	CONSTRAINT ck_payment_orders_channel CHECK (
		channel IN ('mock', 'stripe', 'usdt', 'wechat', 'alipay')
	),
	CONSTRAINT ck_payment_orders_amount CHECK (amount > 0),
	CONSTRAINT ck_payment_orders_risk CHECK (
		risk_status IN ('clear', 'sanctioned', 'large_review')
	),
	CONSTRAINT ck_payment_orders_reconcile CHECK (
		reconcile_status IN ('unchecked', 'matched', 'disputed')
	),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
	FOREIGN KEY(product_id) REFERENCES recharge_products (id) ON DELETE
	SET NULL
);
CREATE INDEX IF NOT EXISTS ix_payment_orders_user_id ON payment_orders (user_id);
COMMENT ON TABLE payment_orders IS '支付订单：法币/加密货币充值单及其对账状态';
COMMENT ON COLUMN payment_orders.id IS '主键（UUID）';
COMMENT ON COLUMN payment_orders.order_no IS '订单号（业务唯一）';
COMMENT ON COLUMN payment_orders.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN payment_orders.product_id IS '充值套餐 ID → recharge_products.id';
COMMENT ON COLUMN payment_orders.channel IS '支付渠道：stripe/crypto_manual 等';
COMMENT ON COLUMN payment_orders.amount IS '金额';
COMMENT ON COLUMN payment_orders.currency IS '币种（ISO 4217，如 USD/CNY）';
COMMENT ON COLUMN payment_orders.bonus_amount IS '赠送金额';
COMMENT ON COLUMN payment_orders.credited_amount IS '实际入账金额';
COMMENT ON COLUMN payment_orders.crypto_amount IS '加密货币数量';
COMMENT ON COLUMN payment_orders.crypto_currency IS '加密货币币种（如 USDT）';
COMMENT ON COLUMN payment_orders.network IS '区块链网络（如 TRC20/ERC20）';
COMMENT ON COLUMN payment_orders.pay_address IS '收款地址';
COMMENT ON COLUMN payment_orders.payer_address IS '付款地址（链上识别）';
COMMENT ON COLUMN payment_orders.status IS '状态：pending/paid/expired/failed';
COMMENT ON COLUMN payment_orders.locked_rate IS '锁仓汇率';
COMMENT ON COLUMN payment_orders.rate_source IS '汇率来源';
COMMENT ON COLUMN payment_orders.locked_at IS '汇率锁定时间';
COMMENT ON COLUMN payment_orders.expires_at IS '过期时间（UTC）';
COMMENT ON COLUMN payment_orders.provider_ref IS '支付网关侧订单号';
COMMENT ON COLUMN payment_orders.tx_hash IS '链上交易哈希';
COMMENT ON COLUMN payment_orders.confirmations IS '区块确认数';
COMMENT ON COLUMN payment_orders.actual_amount IS '实际到账金额';
COMMENT ON COLUMN payment_orders.risk_status IS '风控状态';
COMMENT ON COLUMN payment_orders.reconcile_status IS '对账状态';
COMMENT ON COLUMN payment_orders.idempotency_key IS '幂等键';
COMMENT ON COLUMN payment_orders.request_hash IS '请求体哈希（幂等校验）';
COMMENT ON COLUMN payment_orders.paid_at IS '支付完成时间';
COMMENT ON COLUMN payment_orders.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN payment_orders.updated_at IS '更新时间（UTC）';
COMMENT ON INDEX ix_payment_orders_user_id IS '按用户查询支付订单';
-- ========== 模型与上游 ==========
CREATE TABLE provider_credentials (
	id UUID NOT NULL,
	provider_id UUID NOT NULL,
	label VARCHAR(128) NOT NULL,
	secret_ciphertext TEXT NOT NULL,
	secret_hint VARCHAR(32) NOT NULL,
	status VARCHAR(16) NOT NULL DEFAULT 'active',
	last_used_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_provider_credentials_status CHECK (status IN ('active', 'revoked')),
	FOREIGN KEY(provider_id) REFERENCES providers (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_provider_credentials_provider_id ON provider_credentials (provider_id);
COMMENT ON TABLE provider_credentials IS '上游供应商密钥（密文存储）';
COMMENT ON COLUMN provider_credentials.id IS '主键（UUID）';
COMMENT ON COLUMN provider_credentials.provider_id IS '供应商 ID → providers.id';
COMMENT ON COLUMN provider_credentials.label IS '密钥备注名';
COMMENT ON COLUMN provider_credentials.secret_ciphertext IS '密钥密文（加密存储）';
COMMENT ON COLUMN provider_credentials.secret_hint IS '密钥提示（如 sk-...1234）';
COMMENT ON COLUMN provider_credentials.status IS '状态';
COMMENT ON COLUMN provider_credentials.last_used_at IS '最近使用时间';
COMMENT ON COLUMN provider_credentials.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_provider_credentials_provider_id IS '按供应商查询密钥';
-- ========== 账户与认证 ==========
CREATE TABLE role_permissions (
	role_id UUID NOT NULL,
	permission_id UUID NOT NULL,
	PRIMARY KEY (role_id, permission_id),
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE,
	FOREIGN KEY(permission_id) REFERENCES permissions (id) ON DELETE CASCADE
);
COMMENT ON TABLE role_permissions IS '角色-权限映射（多对多）';
COMMENT ON COLUMN role_permissions.role_id IS '角色 ID → roles.id';
COMMENT ON COLUMN role_permissions.permission_id IS '权限 ID → permissions.id';
CREATE TABLE sessions (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	absolute_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	idle_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	revoked_at TIMESTAMP WITH TIME ZONE,
	created_ip VARCHAR(64),
	last_seen_ip VARCHAR(64),
	user_agent TEXT,
	PRIMARY KEY (id),
	CONSTRAINT ck_sessions_token_hash_len CHECK (char_length(token_hash) = 64),
	CONSTRAINT uq_sessions_token_hash UNIQUE (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions (user_id);
COMMENT ON TABLE sessions IS '登录会话：令牌哈希、过期与撤销';
COMMENT ON COLUMN sessions.id IS '主键（UUID）';
COMMENT ON COLUMN sessions.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN sessions.token_hash IS '令牌哈希（不存明文）';
COMMENT ON COLUMN sessions.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN sessions.last_seen_at IS '最近活跃时间';
COMMENT ON COLUMN sessions.absolute_expires_at IS '绝对过期时间（硬上限）';
COMMENT ON COLUMN sessions.idle_expires_at IS '空闲过期时间（滑动窗口）';
COMMENT ON COLUMN sessions.revoked_at IS '撤销时间，NULL 表示有效';
COMMENT ON COLUMN sessions.created_ip IS '创建会话时 IP';
COMMENT ON COLUMN sessions.last_seen_ip IS '最近活跃 IP';
COMMENT ON COLUMN sessions.user_agent IS '客户端 User-Agent';
COMMENT ON INDEX ix_sessions_user_id IS '按用户查询会话';
-- ========== 通知与工单 ==========
CREATE TABLE tickets (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	category VARCHAR(16) NOT NULL,
	subject VARCHAR(160) NOT NULL,
	status VARCHAR(16) NOT NULL DEFAULT 'open',
	priority VARCHAR(16) NOT NULL DEFAULT 'normal',
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_tickets_category CHECK (
		category IN (
			'billing',
			'technical',
			'refund',
			'chain',
			'other'
		)
	),
	CONSTRAINT ck_tickets_status CHECK (
		status IN ('open', 'pending', 'resolved', 'closed')
	),
	CONSTRAINT ck_tickets_priority CHECK (priority IN ('low', 'normal', 'high')),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
COMMENT ON TABLE tickets IS '工单';
COMMENT ON COLUMN tickets.id IS '主键（UUID）';
COMMENT ON COLUMN tickets.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN tickets.category IS '工单分类';
COMMENT ON COLUMN tickets.subject IS '工单主题';
COMMENT ON COLUMN tickets.status IS '状态';
COMMENT ON COLUMN tickets.priority IS '优先级：low/normal/high/urgent';
COMMENT ON COLUMN tickets.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN tickets.updated_at IS '更新时间（UTC）';
-- ========== 账户与认证 ==========
CREATE TABLE totp_recovery_codes (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	code_hash VARCHAR(64) NOT NULL,
	used_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_totp_recovery_code_hash_len CHECK (char_length(code_hash) = 64),
	CONSTRAINT uq_totp_recovery_code_hash UNIQUE (code_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_totp_recovery_codes_user_id ON totp_recovery_codes (user_id);
COMMENT ON TABLE totp_recovery_codes IS 'TOTP 备用恢复码（哈希存储，用后作废）';
COMMENT ON COLUMN totp_recovery_codes.id IS '主键（UUID）';
COMMENT ON COLUMN totp_recovery_codes.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN totp_recovery_codes.code_hash IS '恢复码哈希（不存明文）';
COMMENT ON COLUMN totp_recovery_codes.used_at IS '使用时间，NULL 表示未用';
COMMENT ON COLUMN totp_recovery_codes.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_totp_recovery_codes_user_id IS '按用户查询恢复码';
CREATE TABLE user_profiles (
	user_id UUID NOT NULL,
	display_name VARCHAR(128) NOT NULL DEFAULT '',
	timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
	locale VARCHAR(16) NOT NULL DEFAULT 'zh-CN',
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (user_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
COMMENT ON TABLE user_profiles IS '用户资料：显示名、时区、语言偏好';
COMMENT ON COLUMN user_profiles.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN user_profiles.display_name IS '显示名';
COMMENT ON COLUMN user_profiles.timezone IS '时区（IANA，如 Asia/Shanghai）';
COMMENT ON COLUMN user_profiles.locale IS '语言（如 zh-CN）';
COMMENT ON COLUMN user_profiles.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN user_profiles.updated_at IS '更新时间（UTC）';
CREATE TABLE user_roles (
	user_id UUID NOT NULL,
	role_id UUID NOT NULL,
	granted_by UUID,
	granted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (user_id, role_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE,
	FOREIGN KEY(granted_by) REFERENCES users (id) ON DELETE
	SET NULL
);
COMMENT ON TABLE user_roles IS '用户-角色映射（多对多）';
COMMENT ON COLUMN user_roles.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN user_roles.role_id IS '角色 ID → roles.id';
COMMENT ON COLUMN user_roles.granted_by IS '授权人用户 ID';
COMMENT ON COLUMN user_roles.granted_at IS '授权时间';
-- ========== 计费与账本 ==========
CREATE TABLE balance_holds (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	api_key_id UUID,
	amount NUMERIC(24, 8) NOT NULL,
	committed_amount NUMERIC(24, 8) NOT NULL DEFAULT 0,
	currency VARCHAR(8) NOT NULL,
	idempotency_key VARCHAR(160) NOT NULL,
	status VARCHAR(16) NOT NULL DEFAULT 'held',
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	request_id VARCHAR(64) NOT NULL,
	pricing_version_id UUID,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	closed_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT uq_balance_holds_request UNIQUE (request_id),
	CONSTRAINT uq_balance_holds_idempotency UNIQUE (idempotency_key),
	CONSTRAINT ck_balance_holds_status CHECK (status IN ('held', 'committed', 'released')),
	CONSTRAINT ck_balance_holds_amount CHECK (amount > 0),
	CONSTRAINT ck_balance_holds_committed CHECK (
		committed_amount >= 0
		AND committed_amount <= amount
	),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
	FOREIGN KEY(api_key_id) REFERENCES api_keys (id) ON DELETE
	SET NULL
);
CREATE INDEX IF NOT EXISTS ix_balance_holds_user_id ON balance_holds (user_id);
CREATE INDEX IF NOT EXISTS ix_balance_holds_held_expiry ON balance_holds (expires_at)
WHERE status = 'held';
COMMENT ON TABLE balance_holds IS '余额预扣：请求前冻结、请求后结算核销';
COMMENT ON COLUMN balance_holds.id IS '主键（UUID）';
COMMENT ON COLUMN balance_holds.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN balance_holds.api_key_id IS '发起请求的 API 密钥 ID';
COMMENT ON COLUMN balance_holds.amount IS '金额';
COMMENT ON COLUMN balance_holds.committed_amount IS '已核销金额（结算后）';
COMMENT ON COLUMN balance_holds.currency IS '币种（ISO 4217，如 USD/CNY）';
COMMENT ON COLUMN balance_holds.status IS '状态：open/settled/released/disputed';
COMMENT ON COLUMN balance_holds.expires_at IS '过期时间（UTC）';
COMMENT ON COLUMN balance_holds.request_id IS '关联网关请求 ID';
COMMENT ON COLUMN balance_holds.pricing_version_id IS '预扣时使用的定价版本';
COMMENT ON COLUMN balance_holds.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN balance_holds.closed_at IS '关闭时间';
COMMENT ON INDEX ix_balance_holds_user_id IS '按用户查询预扣记录';
COMMENT ON INDEX ix_balance_holds_held_expiry IS '高并发：过期预扣定时释放扫描（部分索引，只含 held）';
-- ========== 支付与充值 ==========
CREATE TABLE coupon_redemptions (
	id UUID NOT NULL,
	coupon_id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_coupon_redemptions_user UNIQUE (coupon_id, user_id),
	FOREIGN KEY(coupon_id) REFERENCES coupons (id) ON DELETE CASCADE,
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
COMMENT ON TABLE coupon_redemptions IS '优惠券核销记录';
COMMENT ON COLUMN coupon_redemptions.id IS '主键（UUID）';
COMMENT ON COLUMN coupon_redemptions.coupon_id IS '优惠券 ID → coupons.id';
COMMENT ON COLUMN coupon_redemptions.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN coupon_redemptions.created_at IS '创建时间（UTC）';
CREATE TABLE crypto_deposit_intents (
	id UUID NOT NULL,
	order_id UUID NOT NULL,
	address VARCHAR(128) NOT NULL,
	network VARCHAR(16) NOT NULL,
	tail_amount NUMERIC(24, 8) NOT NULL DEFAULT 0,
	tail_status VARCHAR(16) NOT NULL DEFAULT 'reserved',
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_crypto_deposit_intents_order UNIQUE (order_id),
	CONSTRAINT ck_crypto_tail_status CHECK (tail_status IN ('reserved', 'used', 'released')),
	FOREIGN KEY(order_id) REFERENCES payment_orders (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_crypto_tail_open ON crypto_deposit_intents (address, network, tail_amount)
WHERE tail_status = 'reserved';
COMMENT ON TABLE crypto_deposit_intents IS '加密货币充值意向：尾数匹配识别用户转账';
COMMENT ON COLUMN crypto_deposit_intents.id IS '主键（UUID）';
COMMENT ON COLUMN crypto_deposit_intents.order_id IS '关联订单 ID';
COMMENT ON COLUMN crypto_deposit_intents.address IS '收款地址';
COMMENT ON COLUMN crypto_deposit_intents.network IS '区块链网络';
COMMENT ON COLUMN crypto_deposit_intents.tail_amount IS '识别尾数（金额小数部分标识用户）';
COMMENT ON COLUMN crypto_deposit_intents.tail_status IS '尾数状态：open/used/expired';
COMMENT ON COLUMN crypto_deposit_intents.expires_at IS '过期时间（UTC）';
COMMENT ON INDEX uq_crypto_tail_open IS '同一地址+网络只允许一个未使用尾数（部分唯一索引）';
-- ========== 模型与上游 ==========
CREATE TABLE model_deployments (
	id UUID NOT NULL,
	model_id UUID NOT NULL,
	provider_id UUID NOT NULL,
	status VARCHAR(16) NOT NULL DEFAULT 'active',
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_model_deployments_status CHECK (status IN ('active', 'disabled')),
	FOREIGN KEY(model_id) REFERENCES model_catalog (id) ON DELETE CASCADE,
	FOREIGN KEY(provider_id) REFERENCES providers (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_model_deployments_model_id ON model_deployments (model_id);
COMMENT ON TABLE model_deployments IS '模型部署：模型与供应商的多对多发布关系';
COMMENT ON COLUMN model_deployments.id IS '主键（UUID）';
COMMENT ON COLUMN model_deployments.model_id IS '模型 ID → model_catalog.id';
COMMENT ON COLUMN model_deployments.provider_id IS '供应商 ID → providers.id';
COMMENT ON COLUMN model_deployments.status IS '状态：active/disabled';
COMMENT ON COLUMN model_deployments.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_model_deployments_model_id IS '按模型查询部署';
-- ========== 支付与充值 ==========
CREATE TABLE payment_events (
	id UUID NOT NULL,
	order_id UUID,
	source VARCHAR(32) NOT NULL,
	payload_redacted TEXT NOT NULL,
	signature_ok BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(order_id) REFERENCES payment_orders (id) ON DELETE
	SET NULL
);
CREATE INDEX IF NOT EXISTS ix_payment_events_order_id ON payment_events (order_id);
COMMENT ON TABLE payment_events IS '支付回调事件：网关通知原文（脱敏）与验签结果';
COMMENT ON COLUMN payment_events.id IS '主键（UUID）';
COMMENT ON COLUMN payment_events.order_id IS '所属订单 ID → payment_orders.id';
COMMENT ON COLUMN payment_events.source IS '事件来源（webhook 渠道）';
COMMENT ON COLUMN payment_events.payload_redacted IS '回调报文（已脱敏）';
COMMENT ON COLUMN payment_events.signature_ok IS '签名校验是否通过';
COMMENT ON COLUMN payment_events.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_payment_events_order_id IS '按订单查询回调事件';
-- ========== 计费与账本 ==========
CREATE TABLE pricing_versions (
	id UUID NOT NULL,
	model_id UUID NOT NULL,
	version INTEGER NOT NULL,
	currency VARCHAR(8) NOT NULL,
	effective_from TIMESTAMP WITH TIME ZONE NOT NULL,
	effective_to TIMESTAMP WITH TIME ZONE,
	created_by UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	schedule_rules JSONB,
	PRIMARY KEY (id),
	CONSTRAINT uq_pricing_versions_model_version UNIQUE (model_id, version),
	CONSTRAINT ck_pricing_versions_version CHECK (version >= 1),
	FOREIGN KEY(model_id) REFERENCES model_catalog (id) ON DELETE CASCADE,
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE
	SET NULL
);
CREATE INDEX IF NOT EXISTS ix_pricing_versions_model_id ON pricing_versions (model_id);
COMMENT ON TABLE pricing_versions IS '定价版本：按模型维度发布，含时段定价规则';
COMMENT ON COLUMN pricing_versions.id IS '主键（UUID）';
COMMENT ON COLUMN pricing_versions.model_id IS '模型 ID → model_catalog.id';
COMMENT ON COLUMN pricing_versions.version IS '版本号（同一模型递增）';
COMMENT ON COLUMN pricing_versions.currency IS '币种（ISO 4217，如 USD/CNY）';
COMMENT ON COLUMN pricing_versions.effective_from IS '生效时间';
COMMENT ON COLUMN pricing_versions.effective_to IS '失效时间，NULL 表示当前生效';
COMMENT ON COLUMN pricing_versions.created_by IS '创建人用户 ID';
COMMENT ON COLUMN pricing_versions.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN pricing_versions.schedule_rules IS '时段定价规则（JSONB，UTC 时段 + 节假日排除）';
COMMENT ON INDEX ix_pricing_versions_model_id IS '按模型查询定价版本';
-- ========== 支付与充值 ==========
CREATE TABLE refund_orders (
	id UUID NOT NULL,
	order_id UUID NOT NULL,
	amount NUMERIC(24, 8) NOT NULL,
	currency VARCHAR(8) NOT NULL,
	status VARCHAR(16) NOT NULL DEFAULT 'requested',
	requested_by UUID NOT NULL,
	reviewed_by UUID,
	executed_by UUID,
	destination_address VARCHAR(128) NOT NULL DEFAULT '',
	tx_hash VARCHAR(128),
	reason VARCHAR(256) NOT NULL DEFAULT '',
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	reviewed_at TIMESTAMP WITH TIME ZONE,
	executed_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT uq_refund_orders_order UNIQUE (order_id),
	CONSTRAINT ck_refund_orders_status CHECK (
		status IN ('requested', 'reviewed', 'executed', 'rejected')
	),
	CONSTRAINT ck_refund_orders_amount CHECK (amount > 0),
	CONSTRAINT ck_refund_orders_executor CHECK (
		executed_by IS NULL
		OR executed_by <> requested_by
	),
	CONSTRAINT ck_refund_orders_reviewer CHECK (
		reviewed_by IS NULL
		OR reviewed_by <> requested_by
	),
	FOREIGN KEY(order_id) REFERENCES payment_orders (id) ON DELETE RESTRICT,
	FOREIGN KEY(requested_by) REFERENCES users (id),
	FOREIGN KEY(reviewed_by) REFERENCES users (id),
	FOREIGN KEY(executed_by) REFERENCES users (id)
);
COMMENT ON TABLE refund_orders IS '退款单：申请、审核、执行三段式流程';
COMMENT ON COLUMN refund_orders.id IS '主键（UUID）';
COMMENT ON COLUMN refund_orders.order_id IS '原支付订单 ID → payment_orders.id';
COMMENT ON COLUMN refund_orders.amount IS '金额';
COMMENT ON COLUMN refund_orders.currency IS '币种（ISO 4217，如 USD/CNY）';
COMMENT ON COLUMN refund_orders.status IS '状态：requested/approved/executed/rejected';
COMMENT ON COLUMN refund_orders.requested_by IS '申请人用户 ID';
COMMENT ON COLUMN refund_orders.reviewed_by IS '审核人用户 ID';
COMMENT ON COLUMN refund_orders.executed_by IS '执行人用户 ID';
COMMENT ON COLUMN refund_orders.destination_address IS '退款目标地址（加密货币）';
COMMENT ON COLUMN refund_orders.tx_hash IS '退款交易哈希';
COMMENT ON COLUMN refund_orders.reason IS '退款原因';
COMMENT ON COLUMN refund_orders.created_at IS '创建时间（UTC）';
COMMENT ON COLUMN refund_orders.reviewed_at IS '审核时间';
COMMENT ON COLUMN refund_orders.executed_at IS '执行时间';
-- ========== 通知与工单 ==========
CREATE TABLE ticket_messages (
	id UUID NOT NULL,
	ticket_id UUID NOT NULL,
	author_id UUID NOT NULL,
	body TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_ticket_messages_ticket_id ON ticket_messages (ticket_id);
COMMENT ON TABLE ticket_messages IS '工单消息';
COMMENT ON COLUMN ticket_messages.id IS '主键（UUID）';
COMMENT ON COLUMN ticket_messages.ticket_id IS '所属工单 ID → tickets.id';
COMMENT ON COLUMN ticket_messages.author_id IS '发言人用户 ID';
COMMENT ON COLUMN ticket_messages.body IS '消息内容';
COMMENT ON COLUMN ticket_messages.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_ticket_messages_ticket_id IS '按工单查询消息';
-- ========== 计费与账本 ==========
CREATE TABLE usage_records (
	id UUID NOT NULL,
	request_id VARCHAR(64) NOT NULL,
	user_id UUID NOT NULL,
	api_key_id UUID,
	model_id VARCHAR(128),
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ended_at TIMESTAMP WITH TIME ZONE,
	input_tokens INTEGER NOT NULL DEFAULT 0,
	output_tokens INTEGER NOT NULL DEFAULT 0,
	cached_tokens INTEGER NOT NULL DEFAULT 0,
	user_charge NUMERIC(24, 8),
	currency VARCHAR(8) NOT NULL DEFAULT 'USD',
	http_status INTEGER,
	latency_ms INTEGER,
	first_token_ms INTEGER,
	is_stream BOOLEAN NOT NULL DEFAULT FALSE,
	settlement_status VARCHAR(16) NOT NULL DEFAULT 'pending',
	pricing_version_id UUID,
	unit_price_snapshot TEXT,
	provider_cost NUMERIC(24, 8),
	usage_source VARCHAR(16),
	finish_reason VARCHAR(64),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_usage_records_settlement CHECK (
		settlement_status IN ('pending', 'settled', 'released', 'disputed')
	),
	CONSTRAINT uq_usage_records_request_id UNIQUE (request_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(api_key_id) REFERENCES api_keys (id) ON DELETE
	SET NULL
);
CREATE INDEX IF NOT EXISTS ix_usage_records_unsettled ON usage_records (created_at)
WHERE settlement_status IN ('pending', 'disputed');
CREATE INDEX IF NOT EXISTS ix_usage_records_user_created ON usage_records (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_usage_records_user_id ON usage_records (user_id);
CREATE INDEX IF NOT EXISTS ix_usage_records_model_created ON usage_records (model_id, created_at);
COMMENT ON TABLE usage_records IS '用量记录：每次模型调用的 token 数、费用与结算状态';
COMMENT ON COLUMN usage_records.id IS '主键（UUID）';
COMMENT ON COLUMN usage_records.request_id IS '网关请求 ID（唯一）';
COMMENT ON COLUMN usage_records.user_id IS '所属用户 ID → users.id';
COMMENT ON COLUMN usage_records.model_id IS '调用模型（model_catalog.public_name）';
COMMENT ON COLUMN usage_records.started_at IS '请求开始时间';
COMMENT ON COLUMN usage_records.ended_at IS '请求结束时间';
COMMENT ON COLUMN usage_records.input_tokens IS '输入 token 数';
COMMENT ON COLUMN usage_records.output_tokens IS '输出 token 数';
COMMENT ON COLUMN usage_records.cached_tokens IS '缓存命中 token 数（按缓存价计费）';
COMMENT ON COLUMN usage_records.user_charge IS '用户实扣金额';
COMMENT ON COLUMN usage_records.currency IS '币种（ISO 4217，如 USD/CNY）';
COMMENT ON COLUMN usage_records.http_status IS '上游响应 HTTP 状态码';
COMMENT ON COLUMN usage_records.latency_ms IS '总耗时（毫秒）';
COMMENT ON COLUMN usage_records.first_token_ms IS '首 token 耗时（毫秒，流式）';
COMMENT ON COLUMN usage_records.is_stream IS '是否流式请求';
COMMENT ON COLUMN usage_records.settlement_status IS '结算状态：settled/disputed/refunded';
COMMENT ON COLUMN usage_records.pricing_version_id IS '结算时使用的定价版本';
COMMENT ON COLUMN usage_records.unit_price_snapshot IS '单价快照（JSON，含时段命中信息）';
COMMENT ON COLUMN usage_records.provider_cost IS '上游成本（毛利分析用）';
COMMENT ON COLUMN usage_records.usage_source IS '用量来源：reported（上游返回）/estimated（估算）';
COMMENT ON COLUMN usage_records.finish_reason IS '结束原因：stop/length/error 等';
COMMENT ON COLUMN usage_records.created_at IS '创建时间（UTC）';
COMMENT ON INDEX ix_usage_records_unsettled IS '高并发：未完结结算定时扫描（部分索引，只含 pending/disputed）';
COMMENT ON INDEX ix_usage_records_user_created IS '高并发：用户按时间倒序翻页自己的用量历史';
COMMENT ON INDEX ix_usage_records_user_id IS '按用户查询用量记录';
COMMENT ON INDEX ix_usage_records_model_created IS '高并发：运营按模型维度统计用量';
CREATE TABLE model_prices (
	id UUID NOT NULL,
	pricing_version_id UUID NOT NULL,
	meter VARCHAR(32) NOT NULL,
	unit_price NUMERIC(24, 8) NOT NULL,
	cost_price NUMERIC(24, 8) NOT NULL,
	min_billable_units INTEGER NOT NULL DEFAULT 0,
	tier_min_tokens INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY (id),
	CONSTRAINT uq_model_prices_version_meter_tier UNIQUE (pricing_version_id, meter, tier_min_tokens),
	CONSTRAINT ck_model_prices_meter CHECK (
		meter IN (
			'input_token',
			'output_token',
			'cached_input_token',
			'image'
		)
	),
	CONSTRAINT ck_model_prices_nonnegative CHECK (
		unit_price >= 0
		AND cost_price >= 0
	),
	CONSTRAINT ck_model_prices_min_units CHECK (min_billable_units >= 0),
	CONSTRAINT ck_model_prices_tier_min CHECK (tier_min_tokens >= 0),
	FOREIGN KEY(pricing_version_id) REFERENCES pricing_versions (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_model_prices_pricing_version_id ON model_prices (pricing_version_id);
COMMENT ON TABLE model_prices IS '模型价格明细：按 meter 与阶梯档位定义单价';
COMMENT ON COLUMN model_prices.id IS '主键（UUID）';
COMMENT ON COLUMN model_prices.pricing_version_id IS '所属定价版本 ID';
COMMENT ON COLUMN model_prices.meter IS '计费维度：input_token/output_token/cached_input_token/per_request';
COMMENT ON COLUMN model_prices.unit_price IS '售价单价（每 token 或每次，USD）';
COMMENT ON COLUMN model_prices.cost_price IS '成本单价（毛利分析用）';
COMMENT ON COLUMN model_prices.min_billable_units IS '最小计费单位数';
COMMENT ON COLUMN model_prices.tier_min_tokens IS '阶梯档位下限（输入 token 数 ≥ 此值命中该档）';
COMMENT ON INDEX ix_model_prices_pricing_version_id IS '按定价版本查询价格明细';
CREATE TABLE usage_settlements (
	id UUID NOT NULL,
	usage_record_id UUID NOT NULL,
	status VARCHAR(16) NOT NULL,
	hold_id UUID,
	ledger_entry_id UUID,
	settled_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_usage_settlements_status CHECK (
		status IN ('pending', 'settled', 'released', 'disputed')
	),
	FOREIGN KEY(usage_record_id) REFERENCES usage_records (id) ON DELETE CASCADE,
	FOREIGN KEY(hold_id) REFERENCES balance_holds (id) ON DELETE
	SET NULL,
		FOREIGN KEY(ledger_entry_id) REFERENCES account_ledger (id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_usage_settlements_hold_id ON usage_settlements (hold_id);
CREATE INDEX IF NOT EXISTS ix_usage_settlements_usage_record_id ON usage_settlements (usage_record_id);
COMMENT ON TABLE usage_settlements IS '用量结算：用量记录与账本条目/预扣的关联';
COMMENT ON COLUMN usage_settlements.id IS '主键（UUID）';
COMMENT ON COLUMN usage_settlements.status IS '状态';
COMMENT ON INDEX ix_usage_settlements_hold_id IS '高并发：结算记录按预扣反查';
COMMENT ON INDEX ix_usage_settlements_usage_record_id IS '按用量记录查询结算';
-- ============================================================
-- 第三部分：account_ledger 只追加保护触发器
-- 账本是资金事实来源，禁止 UPDATE / DELETE，只能 INSERT
-- ============================================================
CREATE OR REPLACE FUNCTION _reject_ledger_write() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'account_ledger is append-only; UPDATE/DELETE are not allowed';
END;
$$ LANGUAGE plpgsql;
COMMENT ON FUNCTION _reject_ledger_write() IS '账本只追加保护：拒绝 UPDATE/DELETE';
DROP TRIGGER IF EXISTS trg_reject_ledger_update ON account_ledger;
CREATE TRIGGER trg_reject_ledger_update BEFORE
UPDATE ON account_ledger FOR EACH ROW EXECUTE FUNCTION _reject_ledger_write();
DROP TRIGGER IF EXISTS trg_reject_ledger_delete ON account_ledger;
CREATE TRIGGER trg_reject_ledger_delete BEFORE DELETE ON account_ledger FOR EACH ROW EXECUTE FUNCTION _reject_ledger_write();
-- ============================================================
-- 第四部分：基础种子 + 测试模拟数据（幂等，可重复执行）
-- ============================================================
BEGIN;
INSERT INTO roles (
		id,
		code,
		name,
		description,
		is_system,
		created_at
	)
VALUES (
		'00000000-0000-4000-8000-000000000001',
		'user',
		'User',
		'',
		TRUE,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO roles (
		id,
		code,
		name,
		description,
		is_system,
		created_at
	)
VALUES (
		'00000000-0000-4000-8000-000000000002',
		'support',
		'Support',
		'',
		TRUE,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO roles (
		id,
		code,
		name,
		description,
		is_system,
		created_at
	)
VALUES (
		'00000000-0000-4000-8000-000000000003',
		'finance',
		'Finance',
		'',
		TRUE,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO roles (
		id,
		code,
		name,
		description,
		is_system,
		created_at
	)
VALUES (
		'00000000-0000-4000-8000-000000000004',
		'operator',
		'Operator',
		'',
		TRUE,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO roles (
		id,
		code,
		name,
		description,
		is_system,
		created_at
	)
VALUES (
		'00000000-0000-4000-8000-000000000005',
		'model_ops',
		'Model ops',
		'',
		TRUE,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO roles (
		id,
		code,
		name,
		description,
		is_system,
		created_at
	)
VALUES (
		'00000000-0000-4000-8000-000000000006',
		'admin',
		'Admin',
		'',
		TRUE,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO roles (
		id,
		code,
		name,
		description,
		is_system,
		created_at
	)
VALUES (
		'00000000-0000-4000-8000-000000000007',
		'superadmin',
		'Superadmin',
		'',
		TRUE,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO permissions (id, code, description, created_at)
VALUES (
		'00000000-0000-4000-8000-000000000101',
		'admin:access',
		'Access admin APIs',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO permissions (id, code, description, created_at)
VALUES (
		'00000000-0000-4000-8000-000000000102',
		'user:ban',
		'Freeze or unfreeze users',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO permissions (id, code, description, created_at)
VALUES (
		'00000000-0000-4000-8000-000000000103',
		'ledger:adjust',
		'Adjust ledger',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO permissions (id, code, description, created_at)
VALUES (
		'00000000-0000-4000-8000-000000000104',
		'provider:credential:read',
		'Read provider credentials',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO permissions (id, code, description, created_at)
VALUES (
		'00000000-0000-4000-8000-000000000105',
		'rbac:assign',
		'Assign roles',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO permissions (id, code, description, created_at)
VALUES (
		'00000000-0000-4000-8000-000000000106',
		'refund:request',
		'Request refunds',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO permissions (id, code, description, created_at)
VALUES (
		'00000000-0000-4000-8000-000000000107',
		'refund:execute',
		'Execute refunds',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO permissions (id, code, description, created_at)
VALUES (
		'00000000-0000-4000-8000-000000000108',
		'provider:manage',
		'Manage providers and endpoint allowlist',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO permissions (id, code, description, created_at)
VALUES (
		'00000000-0000-4000-8000-000000000109',
		'model:publish',
		'Confirm and publish models',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000003',
		'00000000-0000-4000-8000-000000000106'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000005',
		'00000000-0000-4000-8000-000000000104'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000005',
		'00000000-0000-4000-8000-000000000108'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000005',
		'00000000-0000-4000-8000-000000000109'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000006',
		'00000000-0000-4000-8000-000000000101'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000006',
		'00000000-0000-4000-8000-000000000107'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000006',
		'00000000-0000-4000-8000-000000000102'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000006',
		'00000000-0000-4000-8000-000000000105'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000006',
		'00000000-0000-4000-8000-000000000108'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000006',
		'00000000-0000-4000-8000-000000000109'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000007',
		'00000000-0000-4000-8000-000000000101'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000007',
		'00000000-0000-4000-8000-000000000102'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000007',
		'00000000-0000-4000-8000-000000000105'
	) ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
VALUES (
		'00000000-0000-4000-8000-000000000007',
		'00000000-0000-4000-8000-000000000103'
	) ON CONFLICT DO NOTHING;
INSERT INTO audit_chain_lock (id)
VALUES (1) ON CONFLICT DO NOTHING;
INSERT INTO content_safety_settings (id, enabled)
VALUES (1, FALSE) ON CONFLICT DO NOTHING;
-- ============================================================
-- 测试用户（密码统一 admin123）
-- ============================================================
INSERT INTO users (
		id,
		email,
		email_normalized,
		password_hash,
		status,
		failed_login_count,
		totp_enabled,
		created_at,
		updated_at
	)
VALUES (
		'11111111-1111-4111-8000-111111111111',
		'admin@forge.local',
		'admin@forge.local',
		'$argon2id$v=19$m=65536,t=3,p=4$0Y2zGM2APoQQXvuHofP/cw$aftvvRuFB5qgN0A37LHVKfr8hHISGZi3+hBbhwMoGJc',
		'active',
		0,
		FALSE,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO user_profiles (
		user_id,
		display_name,
		timezone,
		locale,
		created_at,
		updated_at
	)
VALUES (
		'11111111-1111-4111-8000-111111111111',
		'System Admin',
		'UTC',
		'zh-CN',
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id) DO NOTHING;
INSERT INTO user_roles (user_id, role_id, granted_at)
VALUES (
		'11111111-1111-4111-8000-111111111111',
		'00000000-0000-4000-8000-000000000007',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT DO NOTHING;
INSERT INTO user_roles (user_id, role_id, granted_at)
VALUES (
		'11111111-1111-4111-8000-111111111111',
		'00000000-0000-4000-8000-000000000006',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT DO NOTHING;
INSERT INTO users (
		id,
		email,
		email_normalized,
		password_hash,
		status,
		failed_login_count,
		totp_enabled,
		created_at,
		updated_at
	)
VALUES (
		'22222222-2222-4222-8000-222222222222',
		'operator@forge.local',
		'operator@forge.local',
		'$argon2id$v=19$m=65536,t=3,p=4$0Y2zGM2APoQQXvuHofP/cw$aftvvRuFB5qgN0A37LHVKfr8hHISGZi3+hBbhwMoGJc',
		'active',
		0,
		FALSE,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO user_profiles (
		user_id,
		display_name,
		timezone,
		locale,
		created_at,
		updated_at
	)
VALUES (
		'22222222-2222-4222-8000-222222222222',
		'运维操作员',
		'UTC',
		'zh-CN',
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id) DO NOTHING;
INSERT INTO user_roles (user_id, role_id, granted_at)
VALUES (
		'22222222-2222-4222-8000-222222222222',
		'00000000-0000-4000-8000-000000000004',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT DO NOTHING;
INSERT INTO users (
		id,
		email,
		email_normalized,
		password_hash,
		status,
		failed_login_count,
		totp_enabled,
		created_at,
		updated_at
	)
VALUES (
		'33333333-3333-4333-8000-333333333333',
		'modelops@forge.local',
		'modelops@forge.local',
		'$argon2id$v=19$m=65536,t=3,p=4$0Y2zGM2APoQQXvuHofP/cw$aftvvRuFB5qgN0A37LHVKfr8hHISGZi3+hBbhwMoGJc',
		'active',
		0,
		FALSE,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO user_profiles (
		user_id,
		display_name,
		timezone,
		locale,
		created_at,
		updated_at
	)
VALUES (
		'33333333-3333-4333-8000-333333333333',
		'模型运维',
		'UTC',
		'zh-CN',
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id) DO NOTHING;
INSERT INTO user_roles (user_id, role_id, granted_at)
VALUES (
		'33333333-3333-4333-8000-333333333333',
		'00000000-0000-4000-8000-000000000005',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT DO NOTHING;
INSERT INTO users (
		id,
		email,
		email_normalized,
		password_hash,
		status,
		failed_login_count,
		totp_enabled,
		created_at,
		updated_at
	)
VALUES (
		'44444444-4444-4444-8000-444444444444',
		'finance@forge.local',
		'finance@forge.local',
		'$argon2id$v=19$m=65536,t=3,p=4$0Y2zGM2APoQQXvuHofP/cw$aftvvRuFB5qgN0A37LHVKfr8hHISGZi3+hBbhwMoGJc',
		'active',
		0,
		FALSE,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO user_profiles (
		user_id,
		display_name,
		timezone,
		locale,
		created_at,
		updated_at
	)
VALUES (
		'44444444-4444-4444-8000-444444444444',
		'财务',
		'UTC',
		'zh-CN',
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id) DO NOTHING;
INSERT INTO user_roles (user_id, role_id, granted_at)
VALUES (
		'44444444-4444-4444-8000-444444444444',
		'00000000-0000-4000-8000-000000000003',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT DO NOTHING;
INSERT INTO users (
		id,
		email,
		email_normalized,
		password_hash,
		status,
		failed_login_count,
		totp_enabled,
		created_at,
		updated_at
	)
VALUES (
		'55555555-5555-4555-8000-555555555555',
		'support@forge.local',
		'support@forge.local',
		'$argon2id$v=19$m=65536,t=3,p=4$0Y2zGM2APoQQXvuHofP/cw$aftvvRuFB5qgN0A37LHVKfr8hHISGZi3+hBbhwMoGJc',
		'active',
		0,
		FALSE,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO user_profiles (
		user_id,
		display_name,
		timezone,
		locale,
		created_at,
		updated_at
	)
VALUES (
		'55555555-5555-4555-8000-555555555555',
		'客服支持',
		'UTC',
		'zh-CN',
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id) DO NOTHING;
INSERT INTO user_roles (user_id, role_id, granted_at)
VALUES (
		'55555555-5555-4555-8000-555555555555',
		'00000000-0000-4000-8000-000000000002',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT DO NOTHING;
INSERT INTO users (
		id,
		email,
		email_normalized,
		password_hash,
		status,
		failed_login_count,
		totp_enabled,
		created_at,
		updated_at
	)
VALUES (
		'aaaaaaaa-aaaa-4aaa-8000-aaaaaaaaaaaa',
		'alice@test.dev',
		'alice@test.dev',
		'$argon2id$v=19$m=65536,t=3,p=4$0Y2zGM2APoQQXvuHofP/cw$aftvvRuFB5qgN0A37LHVKfr8hHISGZi3+hBbhwMoGJc',
		'active',
		0,
		FALSE,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO user_profiles (
		user_id,
		display_name,
		timezone,
		locale,
		created_at,
		updated_at
	)
VALUES (
		'aaaaaaaa-aaaa-4aaa-8000-aaaaaaaaaaaa',
		'Alice',
		'UTC',
		'zh-CN',
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id) DO NOTHING;
INSERT INTO user_roles (user_id, role_id, granted_at)
VALUES (
		'aaaaaaaa-aaaa-4aaa-8000-aaaaaaaaaaaa',
		'00000000-0000-4000-8000-000000000001',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT DO NOTHING;
INSERT INTO users (
		id,
		email,
		email_normalized,
		password_hash,
		status,
		failed_login_count,
		totp_enabled,
		created_at,
		updated_at
	)
VALUES (
		'bbbbbbbb-bbbb-4bbb-8000-bbbbbbbbbbbb',
		'bob@test.dev',
		'bob@test.dev',
		'$argon2id$v=19$m=65536,t=3,p=4$0Y2zGM2APoQQXvuHofP/cw$aftvvRuFB5qgN0A37LHVKfr8hHISGZi3+hBbhwMoGJc',
		'active',
		0,
		FALSE,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO user_profiles (
		user_id,
		display_name,
		timezone,
		locale,
		created_at,
		updated_at
	)
VALUES (
		'bbbbbbbb-bbbb-4bbb-8000-bbbbbbbbbbbb',
		'Bob',
		'UTC',
		'zh-CN',
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id) DO NOTHING;
INSERT INTO user_roles (user_id, role_id, granted_at)
VALUES (
		'bbbbbbbb-bbbb-4bbb-8000-bbbbbbbbbbbb',
		'00000000-0000-4000-8000-000000000001',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT DO NOTHING;
INSERT INTO users (
		id,
		email,
		email_normalized,
		password_hash,
		status,
		failed_login_count,
		totp_enabled,
		created_at,
		updated_at
	)
VALUES (
		'cccccccc-cccc-4ccc-8000-cccccccccccc',
		'carol@test.dev',
		'carol@test.dev',
		'$argon2id$v=19$m=65536,t=3,p=4$0Y2zGM2APoQQXvuHofP/cw$aftvvRuFB5qgN0A37LHVKfr8hHISGZi3+hBbhwMoGJc',
		'active',
		0,
		FALSE,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO user_profiles (
		user_id,
		display_name,
		timezone,
		locale,
		created_at,
		updated_at
	)
VALUES (
		'cccccccc-cccc-4ccc-8000-cccccccccccc',
		'Carol',
		'UTC',
		'zh-CN',
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id) DO NOTHING;
INSERT INTO user_roles (user_id, role_id, granted_at)
VALUES (
		'cccccccc-cccc-4ccc-8000-cccccccccccc',
		'00000000-0000-4000-8000-000000000001',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT DO NOTHING;
-- ============================================================
-- 用户初始余额（USD）
-- ============================================================
INSERT INTO account_balances (
		user_id,
		currency,
		balance,
		held,
		frozen,
		updated_at
	)
VALUES (
		'aaaaaaaa-aaaa-4aaa-8000-aaaaaaaaaaaa',
		'USD',
		1000.00000000,
		0,
		0,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id, currency) DO NOTHING;
INSERT INTO account_balances (
		user_id,
		currency,
		balance,
		held,
		frozen,
		updated_at
	)
VALUES (
		'bbbbbbbb-bbbb-4bbb-8000-bbbbbbbbbbbb',
		'USD',
		500.00000000,
		0,
		0,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id, currency) DO NOTHING;
INSERT INTO account_balances (
		user_id,
		currency,
		balance,
		held,
		frozen,
		updated_at
	)
VALUES (
		'cccccccc-cccc-4ccc-8000-cccccccccccc',
		'USD',
		50.00000000,
		0,
		0,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (user_id, currency) DO NOTHING;
-- ============================================================
-- 测试上游供应商
-- ============================================================
INSERT INTO providers (
		id,
		name,
		kind,
		base_url,
		protocol,
		status,
		timeout_seconds,
		priority,
		weight,
		created_at,
		updated_at
	)
VALUES (
		'dddddddd-dddd-4ddd-8000-dddddddddddd',
		'deepseek',
		'compatible',
		'https://api.deepseek.com/v1',
		'openai',
		'active',
		60,
		100,
		1,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO providers (
		id,
		name,
		kind,
		base_url,
		protocol,
		status,
		timeout_seconds,
		priority,
		weight,
		created_at,
		updated_at
	)
VALUES (
		'eeeeeeee-eeee-4eee-8000-eeeeeeeeeeee',
		'openrouter',
		'compatible',
		'https://openrouter.ai/api/v1',
		'openai',
		'active',
		60,
		100,
		1,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO providers (
		id,
		name,
		kind,
		base_url,
		protocol,
		status,
		timeout_seconds,
		priority,
		weight,
		created_at,
		updated_at
	)
VALUES (
		'ffffffff-ffff-4fff-8000-ffffffffffff',
		'ollama-local',
		'ollama',
		'http://127.0.0.1:11434/v1',
		'openai',
		'active',
		60,
		100,
		1,
		'2026-11-02 04:53:35+00',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
-- ============================================================
-- 测试模型目录
-- ============================================================
INSERT INTO model_catalog (
		id,
		provider_id,
		public_name,
		display_name,
		upstream_name,
		status,
		supports_stream,
		supports_tools,
		supports_vision,
		supports_embeddings,
		supports_images,
		context_window,
		max_output,
		created_at
	)
VALUES (
		'aaaabbbb-aaaa-4bbb-8000-aaaabbbb0001',
		'dddddddd-dddd-4ddd-8000-dddddddddddd',
		'DeepSeek Flash V4.1',
		'DeepSeek Flash V4.1',
		'deepseek-flash',
		'published',
		True,
		False,
		False,
		False,
		False,
		65536,
		8192,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO model_catalog (
		id,
		provider_id,
		public_name,
		display_name,
		upstream_name,
		status,
		supports_stream,
		supports_tools,
		supports_vision,
		supports_embeddings,
		supports_images,
		context_window,
		max_output,
		created_at
	)
VALUES (
		'aaaabbbb-aaaa-4bbb-8000-aaaabbbb0002',
		'dddddddd-dddd-4ddd-8000-dddddddddddd',
		'DeepSeek V4 Pro',
		'DeepSeek V4 Pro',
		'deepseek-v4-pro',
		'published',
		True,
		False,
		False,
		False,
		False,
		65536,
		8192,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO model_catalog (
		id,
		provider_id,
		public_name,
		display_name,
		upstream_name,
		status,
		supports_stream,
		supports_tools,
		supports_vision,
		supports_embeddings,
		supports_images,
		context_window,
		max_output,
		created_at
	)
VALUES (
		'aaaabbbb-aaaa-4bbb-8000-aaaabbbb0003',
		'eeeeeeee-eeee-4eee-8000-eeeeeeeeeeee',
		'OpenRouter GPT-4o',
		'OpenRouter GPT-4o',
		'openai/gpt-4o',
		'published',
		True,
		True,
		True,
		False,
		False,
		128000,
		4096,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO model_catalog (
		id,
		provider_id,
		public_name,
		display_name,
		upstream_name,
		status,
		supports_stream,
		supports_tools,
		supports_vision,
		supports_embeddings,
		supports_images,
		context_window,
		max_output,
		created_at
	)
VALUES (
		'aaaabbbb-aaaa-4bbb-8000-aaaabbbb0004',
		'ffffffff-ffff-4fff-8000-ffffffffffff',
		'Llama 3.1 8B',
		'Llama 3.1 8B',
		'llama3.1:8b',
		'published',
		True,
		True,
		False,
		False,
		False,
		8192,
		4096,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
-- ============================================================
-- 测试充值套餐
-- ============================================================
INSERT INTO recharge_products (
		id,
		name,
		amount,
		currency,
		bonus_amount,
		enabled,
		sort_order,
		created_at
	)
VALUES (
		'cccccccc-cccc-4ddd-8000-cccccccc0001',
		'基础包 $10',
		10.00000000,
		'USD',
		0,
		TRUE,
		1,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO recharge_products (
		id,
		name,
		amount,
		currency,
		bonus_amount,
		enabled,
		sort_order,
		created_at
	)
VALUES (
		'cccccccc-cccc-4ddd-8000-cccccccc0002',
		'标准包 $50',
		50.00000000,
		'USD',
		5.00000000,
		TRUE,
		2,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO recharge_products (
		id,
		name,
		amount,
		currency,
		bonus_amount,
		enabled,
		sort_order,
		created_at
	)
VALUES (
		'cccccccc-cccc-4ddd-8000-cccccccc0003',
		'高级包 $100',
		100.00000000,
		'USD',
		15.00000000,
		TRUE,
		3,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO recharge_products (
		id,
		name,
		amount,
		currency,
		bonus_amount,
		enabled,
		sort_order,
		created_at
	)
VALUES (
		'cccccccc-cccc-4ddd-8000-cccccccc0004',
		'企业包 $500',
		500.00000000,
		'USD',
		100.00000000,
		TRUE,
		4,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
-- ============================================================
-- 测试公告
-- ============================================================
INSERT INTO announcements (id, slug, title, body, published, created_at)
VALUES (
		'aaaaaaaa-bbbb-4ccc-8000-dddddddddddd',
		'welcome',
		'欢迎使用 Forge API',
		'这是一个测试环境。所有数据都是模拟的，可随时重置。',
		TRUE,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (slug) DO NOTHING;
-- ============================================================
-- 测试优惠券
-- ============================================================
INSERT INTO coupons (
		id,
		code,
		bonus_amount,
		currency,
		max_uses,
		used_count,
		enabled,
		created_at
	)
VALUES (
		'eeeeeeee-ffff-4111-8000-aaaaaaaaaaaa',
		'WELCOME10',
		'10.00000000',
		'USD',
		100,
		0,
		TRUE,
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
-- ============================================================
-- 测试汇率
-- ============================================================
INSERT INTO exchange_rates (
		id,
		base_currency,
		quote_currency,
		rate,
		source,
		captured_at
	)
VALUES (
		'ffffffff-1111-4222-8000-bbbbbbbbbbbb',
		'USD',
		'CNY',
		'7.25000000',
		'manual',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
INSERT INTO exchange_rates (
		id,
		base_currency,
		quote_currency,
		rate,
		source,
		captured_at
	)
VALUES (
		'ffffffff-1111-4222-8000-bbbbbbbbbbbb',
		'CNY',
		'USD',
		'0.13790000',
		'manual',
		'2026-11-02 04:53:35+00'
	) ON CONFLICT (id) DO NOTHING;
COMMIT;
-- ============================================================
-- 测试环境 SQL 执行完毕
-- 测试用户 (密码统一 admin123):
--   admin@forge.local        超级管理员 + 管理员
--   operator@forge.local     运维操作员
--   modelops@forge.local     模型运维
--   finance@forge.local      财务
--   support@forge.local     客服支持
--   alice@test.dev          普通用户 (余额 $1000)
--   bob@test.dev             普通用户 (余额 $500)
--   carol@test.dev           普通用户 (余额 $50)
-- 测试供应商: deepseek / openrouter / ollama-local
-- 测试充值套餐: $10 / $50 (+$5) / $100 (+$15) / $500 (+$100)
-- 优惠券: WELCOME10 (+$10)
-- ============================================================