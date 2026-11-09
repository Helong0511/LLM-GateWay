-- ============================================================
-- Forge API · 初始化第 2 步：建表 + 索引 + 外键 + 触发器 + 种子数据
-- 版本: 2026-11-03
-- 适用: Navicat Premium 17 / pgAdmin / DBeaver / DataGrip
-- 数据库: PostgreSQL 15+
-- 字符集: UTF-8（本文件必须以 UTF-8 无 BOM 保存与导入）
--
-- 执行位置: 连接 forge 库（先执行第 1 步 forge_prod_01_reset_database.sql）
-- 执行用户: forge 用户即可
-- 可重复执行: 开头 DROP SCHEMA public CASCADE 会清空并重建；会校验当前库必须是 forge
--
-- 执行结果:
--   - 50 张表 + 索引 + 外键 + 触发器
--   - alembic_version = 20261102_0017_api_key_crypto
--     （已对齐迁移 head，后续 alembic upgrade head 不会重放历史迁移）
--   - 系统必要数据: 7 个角色、9 个权限、角色权限映射、1 个超级管理员
--   - 超级管理员只分配 superadmin + admin 角色，不分配普通用户角色
--   - 不包含普通用户，也不预置任何模型数据（模型范围使用列默认值）
--
-- 默认超级管理员: admin@forge.local / admin123（首次登录后立即修改密码）
-- ============================================================

-- 安全检查：防止在 postgres 等其它库中误执行本段
DO $$
BEGIN
    IF current_database() <> 'forge' THEN
        RAISE EXCEPTION '当前连接的是 % 库，第 2 段必须在 forge 库中执行，请切换数据库后重试',
            current_database();
    END IF;
END $$;

-- ============================================================
-- 第零部分：清空并重建 public schema
-- DROP SCHEMA CASCADE 会连带删除所有表/索引/触发器/外键
-- CREATE SCHEMA AUTHORIZATION forge 让所有后续 CREATE TABLE 的 owner 自动是 forge
-- ============================================================
DROP SCHEMA public CASCADE;
CREATE SCHEMA public AUTHORIZATION forge;

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;

-- ============================================================
-- 兜底：DEFAULT PRIVILEGES + 给 public 用户组 USAGE
-- ============================================================
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO forge;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO forge;
GRANT USAGE ON SCHEMA public TO public;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';

-- Name: _reject_ledger_write(); Type: FUNCTION; Schema: public; Owner: -

CREATE FUNCTION public._reject_ledger_write() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'account_ledger is append-only; UPDATE/DELETE are not allowed';
END;
$$;

-- Name: FUNCTION _reject_ledger_write(); Type: COMMENT; Schema: public; Owner: -

COMMENT ON FUNCTION public._reject_ledger_write() IS '账本只追加保护：拒绝 UPDATE/DELETE';

SET default_tablespace = '';

SET default_table_access_method = heap;

-- Name: account_balances; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.account_balances (
    user_id uuid NOT NULL,
    currency character varying(8) NOT NULL,
    balance numeric(24,8) DEFAULT 0 NOT NULL,
    held numeric(24,8) DEFAULT 0 NOT NULL,
    frozen numeric(24,8) DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_account_balances_available CHECK ((balance >= (held + frozen))),
    CONSTRAINT ck_account_balances_balance CHECK ((balance >= (0)::numeric)),
    CONSTRAINT ck_account_balances_frozen CHECK ((frozen >= (0)::numeric)),
    CONSTRAINT ck_account_balances_held CHECK ((held >= (0)::numeric))
);

-- Name: TABLE account_balances; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.account_balances IS '账户余额表：可用余额、冻结中预扣、风控冻结';

-- Name: COLUMN account_balances.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_balances.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN account_balances.currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_balances.currency IS '币种（ISO 4217，如 USD/CNY）';

-- Name: COLUMN account_balances.balance; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_balances.balance IS '可用余额';

-- Name: COLUMN account_balances.held; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_balances.held IS '预扣冻结中金额（请求处理中）';

-- Name: COLUMN account_balances.frozen; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_balances.frozen IS '风控冻结金额（不可用）';

-- Name: COLUMN account_balances.updated_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_balances.updated_at IS '更新时间（UTC）';

-- Name: account_ledger; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.account_ledger (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    entry_type character varying(32) NOT NULL,
    direction character varying(1) NOT NULL,
    amount numeric(24,8) NOT NULL,
    currency character varying(8) NOT NULL,
    idempotency_key character varying(160) NOT NULL,
    balance_before numeric(24,8) NOT NULL,
    balance_after numeric(24,8) NOT NULL,
    reference_type character varying(32),
    reference_id character varying(64),
    reason character varying(256) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    created_by uuid,
    CONSTRAINT ck_account_ledger_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_account_ledger_balance CHECK (((balance_before >= (0)::numeric) AND (balance_after >= (0)::numeric))),
    CONSTRAINT ck_account_ledger_direction CHECK (((direction)::text = ANY (ARRAY[('C'::character varying)::text, ('D'::character varying)::text, ('N'::character varying)::text])))
);

-- Name: TABLE account_ledger; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.account_ledger IS '账户账本（只追加）：所有余额变动的唯一事实来源';

-- Name: COLUMN account_ledger.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.id IS '主键（UUID）';

-- Name: COLUMN account_ledger.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN account_ledger.entry_type; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.entry_type IS '条目类型：recharge/consume/refund/adjust/bonus 等';

-- Name: COLUMN account_ledger.direction; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.direction IS '方向：credit（入账）/debit（出账）';

-- Name: COLUMN account_ledger.amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.amount IS '金额';

-- Name: COLUMN account_ledger.currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.currency IS '币种（ISO 4217，如 USD/CNY）';

-- Name: COLUMN account_ledger.idempotency_key; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.idempotency_key IS '幂等键（唯一，防重复入账）';

-- Name: COLUMN account_ledger.balance_before; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.balance_before IS '变动前余额';

-- Name: COLUMN account_ledger.balance_after; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.balance_after IS '变动后余额';

-- Name: COLUMN account_ledger.reference_type; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.reference_type IS '关联单据类型（order/usage/refund 等）';

-- Name: COLUMN account_ledger.reference_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.reference_id IS '关联单据 ID';

-- Name: COLUMN account_ledger.reason; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.reason IS '变动原因备注';

-- Name: COLUMN account_ledger.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.created_at IS '创建时间（UTC）';

-- Name: COLUMN account_ledger.created_by; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.account_ledger.created_by IS '创建人用户 ID';

-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Name: announcements; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.announcements (
    id uuid NOT NULL,
    slug character varying(80) NOT NULL,
    title character varying(160) NOT NULL,
    body text NOT NULL,
    published boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: TABLE announcements; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.announcements IS '平台公告';

-- Name: COLUMN announcements.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.announcements.id IS '主键（UUID）';

-- Name: COLUMN announcements.slug; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.announcements.slug IS '标识（URL 友好，唯一）';

-- Name: COLUMN announcements.title; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.announcements.title IS '标题';

-- Name: COLUMN announcements.body; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.announcements.body IS '正文';

-- Name: COLUMN announcements.published; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.announcements.published IS '是否发布';

-- Name: COLUMN announcements.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.announcements.created_at IS '创建时间（UTC）';

-- Name: api_keys; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.api_keys (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    name character varying(128) NOT NULL,
    key_prefix character varying(24) NOT NULL,
    key_hash character varying(64) NOT NULL,
    key_ciphertext text,
    key_enc_version integer DEFAULT 0 NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    expires_at timestamp with time zone,
    rpm_limit integer,
    tpm_limit integer,
    max_concurrency integer,
    budget_limit numeric(24,8),
    budget_spent numeric(24,8) DEFAULT 0 NOT NULL,
    allowed_models text DEFAULT '[]'::text NOT NULL,
    ip_allowlist text DEFAULT '[]'::text NOT NULL,
    last_used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    revoked_at timestamp with time zone,
    CONSTRAINT ck_api_keys_key_hash_len CHECK ((char_length((key_hash)::text) = 64)),
    CONSTRAINT ck_api_keys_status CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('disabled'::character varying)::text, ('revoked'::character varying)::text, ('expired'::character varying)::text])))
);

-- Name: TABLE api_keys; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.api_keys IS 'API 密钥：哈希存储，含限速/并发/预算/模型白名单';

-- Name: COLUMN api_keys.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.id IS '主键（UUID）';

-- Name: COLUMN api_keys.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN api_keys.name; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.name IS '密钥备注名';

-- Name: COLUMN api_keys.key_prefix; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.key_prefix IS '密钥前缀（展示用，如 sk-abcd）';

-- Name: COLUMN api_keys.key_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.key_hash IS '密钥哈希（SHA-256，用于网关 lookup，不存明文）';

-- Name: COLUMN api_keys.key_ciphertext; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.key_ciphertext IS '密钥 AES-256-GCM 密文（格式 v1|iv|tag|body），NULL=历史无加密（仅 digest）';

-- Name: COLUMN api_keys.key_enc_version; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.key_enc_version IS '加密算法版本：0=无，1=AES-256-GCM';

-- Name: COLUMN api_keys.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.status IS '状态：active/revoked';

-- Name: COLUMN api_keys.expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.expires_at IS '过期时间（UTC）';

-- Name: COLUMN api_keys.rpm_limit; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.rpm_limit IS '每分钟请求数上限';

-- Name: COLUMN api_keys.tpm_limit; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.tpm_limit IS '每分钟 token 数上限';

-- Name: COLUMN api_keys.max_concurrency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.max_concurrency IS '最大并发请求数';

-- Name: COLUMN api_keys.budget_limit; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.budget_limit IS '预算上限（USD），NULL 表示不限';

-- Name: COLUMN api_keys.budget_spent; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.budget_spent IS '已消耗预算';

-- Name: COLUMN api_keys.allowed_models; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.allowed_models IS '已废弃：模型范围改由账号（users.allowed_models）决定，此列固定为空数组';

-- Name: COLUMN api_keys.ip_allowlist; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.ip_allowlist IS 'IP 白名单（JSON 数组，空=不限）';

-- Name: COLUMN api_keys.last_used_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.last_used_at IS '最近使用时间';

-- Name: COLUMN api_keys.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.created_at IS '创建时间（UTC）';

-- Name: COLUMN api_keys.revoked_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.api_keys.revoked_at IS '吊销时间';

-- Name: audit_chain_lock; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.audit_chain_lock (
    id integer NOT NULL
);

-- Name: TABLE audit_chain_lock; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.audit_chain_lock IS '审计哈希链锁：单行表，串行化链尾写入';

-- Name: COLUMN audit_chain_lock.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_chain_lock.id IS '固定为 1（单行锁表）';

-- Name: audit_chain_lock_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.audit_chain_lock_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: audit_chain_lock_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.audit_chain_lock_id_seq OWNED BY public.audit_chain_lock.id;

-- Name: audit_events; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.audit_events (
    id uuid NOT NULL,
    seq integer NOT NULL,
    actor_id uuid,
    action character varying(64) NOT NULL,
    target_type character varying(64) NOT NULL,
    target_id character varying(64) NOT NULL,
    detail character varying(256) DEFAULT ''::character varying NOT NULL,
    prev_hash character varying(64) NOT NULL,
    content_hash character varying(64) NOT NULL,
    recorded_at character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: TABLE audit_events; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.audit_events IS '审计事件（哈希链）：后台敏感操作的不可篡改流水';

-- Name: COLUMN audit_events.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.id IS '主键（UUID）';

-- Name: COLUMN audit_events.seq; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.seq IS '链内序号（严格递增）';

-- Name: COLUMN audit_events.actor_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.actor_id IS '操作人用户 ID';

-- Name: COLUMN audit_events.action; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.action IS '操作类型';

-- Name: COLUMN audit_events.target_type; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.target_type IS '目标对象类型';

-- Name: COLUMN audit_events.target_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.target_id IS '目标对象 ID';

-- Name: COLUMN audit_events.detail; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.detail IS '操作详情（JSON，脱敏）';

-- Name: COLUMN audit_events.prev_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.prev_hash IS '前一条事件哈希（链式防篡改）';

-- Name: COLUMN audit_events.content_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.content_hash IS '本条内容哈希';

-- Name: COLUMN audit_events.recorded_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.recorded_at IS '记录时间';

-- Name: COLUMN audit_events.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.audit_events.created_at IS '创建时间（UTC）';

-- Name: balance_holds; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.balance_holds (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    api_key_id uuid,
    amount numeric(24,8) NOT NULL,
    committed_amount numeric(24,8) DEFAULT 0 NOT NULL,
    currency character varying(8) NOT NULL,
    idempotency_key character varying(160) NOT NULL,
    status character varying(16) DEFAULT 'held'::character varying NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    request_id character varying(64) NOT NULL,
    pricing_version_id uuid,
    created_at timestamp with time zone NOT NULL,
    closed_at timestamp with time zone,
    CONSTRAINT ck_balance_holds_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_balance_holds_committed CHECK (((committed_amount >= (0)::numeric) AND (committed_amount <= amount))),
    CONSTRAINT ck_balance_holds_status CHECK (((status)::text = ANY (ARRAY[('held'::character varying)::text, ('committed'::character varying)::text, ('released'::character varying)::text])))
);

-- Name: TABLE balance_holds; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.balance_holds IS '余额预扣：请求前冻结、请求后结算核销';

-- Name: COLUMN balance_holds.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.id IS '主键（UUID）';

-- Name: COLUMN balance_holds.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN balance_holds.api_key_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.api_key_id IS '发起请求的 API 密钥 ID';

-- Name: COLUMN balance_holds.amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.amount IS '金额';

-- Name: COLUMN balance_holds.committed_amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.committed_amount IS '已核销金额（结算后）';

-- Name: COLUMN balance_holds.currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.currency IS '币种（ISO 4217，如 USD/CNY）';

-- Name: COLUMN balance_holds.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.status IS '状态：open/settled/released/disputed';

-- Name: COLUMN balance_holds.expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.expires_at IS '过期时间（UTC）';

-- Name: COLUMN balance_holds.request_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.request_id IS '关联网关请求 ID';

-- Name: COLUMN balance_holds.pricing_version_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.pricing_version_id IS '预扣时使用的定价版本';

-- Name: COLUMN balance_holds.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.created_at IS '创建时间（UTC）';

-- Name: COLUMN balance_holds.closed_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.balance_holds.closed_at IS '关闭时间';

-- Name: content_audit_records; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.content_audit_records (
    id uuid NOT NULL,
    user_id uuid,
    model_name character varying(128) NOT NULL,
    category character varying(32) NOT NULL,
    summary_hash character varying(64) NOT NULL,
    created_at timestamp with time zone NOT NULL
);

-- Name: TABLE content_audit_records; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.content_audit_records IS '内容审计记录：命中安全策略的请求摘要';

-- Name: COLUMN content_audit_records.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.content_audit_records.id IS '主键（UUID）';

-- Name: COLUMN content_audit_records.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.content_audit_records.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN content_audit_records.model_name; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.content_audit_records.model_name IS '调用模型名';

-- Name: COLUMN content_audit_records.category; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.content_audit_records.category IS '命中类别';

-- Name: COLUMN content_audit_records.summary_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.content_audit_records.summary_hash IS '内容摘要哈希（不存原文）';

-- Name: COLUMN content_audit_records.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.content_audit_records.created_at IS '创建时间（UTC）';

-- Name: content_safety_settings; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.content_safety_settings (
    id integer NOT NULL,
    enabled boolean DEFAULT false NOT NULL
);

-- Name: TABLE content_safety_settings; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.content_safety_settings IS '内容安全开关（单行配置）';

-- Name: COLUMN content_safety_settings.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.content_safety_settings.id IS '主键（UUID）';

-- Name: COLUMN content_safety_settings.enabled; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.content_safety_settings.enabled IS '是否启用内容安全审计';

-- Name: content_safety_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.content_safety_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: content_safety_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.content_safety_settings_id_seq OWNED BY public.content_safety_settings.id;

-- Name: coupon_redemptions; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.coupon_redemptions (
    id uuid NOT NULL,
    coupon_id uuid NOT NULL,
    user_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);

-- Name: TABLE coupon_redemptions; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.coupon_redemptions IS '优惠券核销记录';

-- Name: COLUMN coupon_redemptions.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupon_redemptions.id IS '主键（UUID）';

-- Name: COLUMN coupon_redemptions.coupon_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupon_redemptions.coupon_id IS '优惠券 ID → coupons.id';

-- Name: COLUMN coupon_redemptions.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupon_redemptions.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN coupon_redemptions.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupon_redemptions.created_at IS '创建时间（UTC）';

-- Name: coupons; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.coupons (
    id uuid NOT NULL,
    code character varying(32) NOT NULL,
    bonus_amount numeric(24,8) NOT NULL,
    currency character varying(8) NOT NULL,
    max_uses integer NOT NULL,
    used_count integer DEFAULT 0 NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    expires_at timestamp with time zone,
    deleted_at timestamp with time zone,
    created_by uuid,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_coupons_bonus CHECK ((bonus_amount > (0)::numeric)),
    CONSTRAINT ck_coupons_uses CHECK (((max_uses >= 1) AND (used_count >= 0) AND (used_count <= max_uses)))
);

-- Name: TABLE coupons; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.coupons IS '优惠券：固定面额赠送，限使用次数';

-- Name: COLUMN coupons.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.id IS '主键（UUID）';

-- Name: COLUMN coupons.code; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.code IS '优惠码（唯一）';

-- Name: COLUMN coupons.bonus_amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.bonus_amount IS '赠送金额';

-- Name: COLUMN coupons.currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.currency IS '币种（ISO 4217，如 USD/CNY）';

-- Name: COLUMN coupons.max_uses; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.max_uses IS '最大使用次数';

-- Name: COLUMN coupons.used_count; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.used_count IS '已使用次数';

-- Name: COLUMN coupons.enabled; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.enabled IS '是否启用';

-- Name: COLUMN coupons.expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.expires_at IS '过期时间（UTC）';

-- Name: COLUMN coupons.deleted_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.deleted_at IS '软删除时间，NULL 表示未删除';

-- Name: COLUMN coupons.created_by; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.created_by IS '创建人用户 ID';

-- Name: COLUMN coupons.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.coupons.created_at IS '创建时间（UTC）';

-- Name: crypto_deposit_intents; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.crypto_deposit_intents (
    id uuid NOT NULL,
    order_id uuid NOT NULL,
    address character varying(128) NOT NULL,
    network character varying(16) NOT NULL,
    tail_amount numeric(24,8) DEFAULT 0 NOT NULL,
    tail_status character varying(16) DEFAULT 'reserved'::character varying NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_crypto_tail_status CHECK (((tail_status)::text = ANY (ARRAY[('reserved'::character varying)::text, ('used'::character varying)::text, ('released'::character varying)::text])))
);

-- Name: TABLE crypto_deposit_intents; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.crypto_deposit_intents IS '加密货币充值意向：尾数匹配识别用户转账';

-- Name: COLUMN crypto_deposit_intents.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.crypto_deposit_intents.id IS '主键（UUID）';

-- Name: COLUMN crypto_deposit_intents.order_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.crypto_deposit_intents.order_id IS '关联订单 ID';

-- Name: COLUMN crypto_deposit_intents.address; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.crypto_deposit_intents.address IS '收款地址';

-- Name: COLUMN crypto_deposit_intents.network; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.crypto_deposit_intents.network IS '区块链网络';

-- Name: COLUMN crypto_deposit_intents.tail_amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.crypto_deposit_intents.tail_amount IS '识别尾数（金额小数部分标识用户）';

-- Name: COLUMN crypto_deposit_intents.tail_status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.crypto_deposit_intents.tail_status IS '尾数状态：open/used/expired';

-- Name: COLUMN crypto_deposit_intents.expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.crypto_deposit_intents.expires_at IS '过期时间（UTC）';

-- Name: email_change_tokens; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.email_change_tokens (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    new_email character varying(320) NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    consumed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_email_change_token_hash_len CHECK ((char_length((token_hash)::text) = 64))
);

-- Name: TABLE email_change_tokens; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.email_change_tokens IS '换绑邮箱令牌（哈希存储，一次性）';

-- Name: COLUMN email_change_tokens.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_change_tokens.id IS '主键（UUID）';

-- Name: COLUMN email_change_tokens.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_change_tokens.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN email_change_tokens.new_email; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_change_tokens.new_email IS '待换绑的新邮箱';

-- Name: COLUMN email_change_tokens.token_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_change_tokens.token_hash IS '令牌哈希（不存明文）';

-- Name: COLUMN email_change_tokens.expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_change_tokens.expires_at IS '过期时间（UTC）';

-- Name: COLUMN email_change_tokens.attempt_count; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_change_tokens.attempt_count IS '已尝试验证次数（防爆破）';

-- Name: COLUMN email_change_tokens.consumed_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_change_tokens.consumed_at IS '核销时间，NULL 表示未使用';

-- Name: COLUMN email_change_tokens.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_change_tokens.created_at IS '创建时间（UTC）';

-- Name: email_verification_tokens; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.email_verification_tokens (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    consumed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_email_verification_token_hash_len CHECK ((char_length((token_hash)::text) = 64))
);

-- Name: TABLE email_verification_tokens; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.email_verification_tokens IS '邮箱验证令牌（哈希存储，一次性）';

-- Name: COLUMN email_verification_tokens.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_verification_tokens.id IS '主键（UUID）';

-- Name: COLUMN email_verification_tokens.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_verification_tokens.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN email_verification_tokens.token_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_verification_tokens.token_hash IS '令牌哈希（不存明文）';

-- Name: COLUMN email_verification_tokens.expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_verification_tokens.expires_at IS '过期时间（UTC）';

-- Name: COLUMN email_verification_tokens.attempt_count; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_verification_tokens.attempt_count IS '已尝试验证次数（防爆破）';

-- Name: COLUMN email_verification_tokens.consumed_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_verification_tokens.consumed_at IS '核销时间，NULL 表示未使用';

-- Name: COLUMN email_verification_tokens.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.email_verification_tokens.created_at IS '创建时间（UTC）';

-- Name: endpoint_allowlist; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.endpoint_allowlist (
    id uuid NOT NULL,
    host character varying(255) NOT NULL,
    approved boolean DEFAULT false NOT NULL,
    note character varying(256) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: TABLE endpoint_allowlist; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.endpoint_allowlist IS '上游端点白名单：防止 SSRF 到非授权主机';

-- Name: COLUMN endpoint_allowlist.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.endpoint_allowlist.id IS '主键（UUID）';

-- Name: COLUMN endpoint_allowlist.host; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.endpoint_allowlist.host IS '允许的上游主机名';

-- Name: COLUMN endpoint_allowlist.approved; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.endpoint_allowlist.approved IS '是否已审批';

-- Name: COLUMN endpoint_allowlist.note; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.endpoint_allowlist.note IS '备注';

-- Name: COLUMN endpoint_allowlist.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.endpoint_allowlist.created_at IS '创建时间（UTC）';

-- Name: exchange_rates; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.exchange_rates (
    id uuid NOT NULL,
    base_currency character varying(8) NOT NULL,
    quote_currency character varying(8) NOT NULL,
    rate numeric(24,8) NOT NULL,
    source character varying(64) NOT NULL,
    captured_at timestamp with time zone NOT NULL
);

-- Name: TABLE exchange_rates; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.exchange_rates IS '汇率快照：充值/结算时的币种换算依据';

-- Name: COLUMN exchange_rates.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.exchange_rates.id IS '主键（UUID）';

-- Name: COLUMN exchange_rates.base_currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.exchange_rates.base_currency IS '基准币种';

-- Name: COLUMN exchange_rates.quote_currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.exchange_rates.quote_currency IS '报价币种';

-- Name: COLUMN exchange_rates.rate; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.exchange_rates.rate IS '汇率（1 base = rate quote）';

-- Name: COLUMN exchange_rates.source; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.exchange_rates.source IS '来源（manual/api）';

-- Name: COLUMN exchange_rates.captured_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.exchange_rates.captured_at IS '采集时间';

-- Name: idempotency_records; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.idempotency_records (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    idempotency_key character varying(80) NOT NULL,
    request_hash character varying(64) NOT NULL,
    status_code integer NOT NULL,
    response_body text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL
);

-- Name: TABLE idempotency_records; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.idempotency_records IS '通用幂等记录：防止重复提交造成重复处理';

-- Name: COLUMN idempotency_records.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.idempotency_records.id IS '主键（UUID）';

-- Name: COLUMN idempotency_records.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.idempotency_records.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN idempotency_records.idempotency_key; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.idempotency_records.idempotency_key IS '幂等键';

-- Name: COLUMN idempotency_records.request_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.idempotency_records.request_hash IS '请求体哈希';

-- Name: COLUMN idempotency_records.status_code; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.idempotency_records.status_code IS '已响应的 HTTP 状态码';

-- Name: COLUMN idempotency_records.response_body; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.idempotency_records.response_body IS '已缓存的响应体';

-- Name: COLUMN idempotency_records.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.idempotency_records.created_at IS '创建时间（UTC）';

-- Name: COLUMN idempotency_records.expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.idempotency_records.expires_at IS '过期时间（UTC）';

-- Name: invoice_requests; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.invoice_requests (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    order_no character varying(40) NOT NULL,
    title character varying(160) NOT NULL,
    tax_no character varying(64) DEFAULT ''::character varying NOT NULL,
    amount numeric(24,8) NOT NULL,
    currency character varying(8) NOT NULL,
    status character varying(16) DEFAULT 'requested'::character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_invoice_requests_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_invoice_requests_status CHECK (((status)::text = ANY (ARRAY[('requested'::character varying)::text, ('issued'::character varying)::text, ('rejected'::character varying)::text])))
);

-- Name: TABLE invoice_requests; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.invoice_requests IS '发票申请记录';

-- Name: COLUMN invoice_requests.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.invoice_requests.id IS '主键（UUID）';

-- Name: COLUMN invoice_requests.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.invoice_requests.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN invoice_requests.order_no; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.invoice_requests.order_no IS '关联订单号';

-- Name: COLUMN invoice_requests.title; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.invoice_requests.title IS '发票抬头';

-- Name: COLUMN invoice_requests.tax_no; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.invoice_requests.tax_no IS '税号';

-- Name: COLUMN invoice_requests.amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.invoice_requests.amount IS '金额';

-- Name: COLUMN invoice_requests.currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.invoice_requests.currency IS '币种（ISO 4217，如 USD/CNY）';

-- Name: COLUMN invoice_requests.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.invoice_requests.status IS '状态：pending/issued/rejected';

-- Name: COLUMN invoice_requests.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.invoice_requests.created_at IS '创建时间（UTC）';

-- Name: job_runs; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.job_runs (
    id uuid NOT NULL,
    name character varying(64) NOT NULL,
    status character varying(16) NOT NULL,
    detail character varying(256) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_job_runs_status CHECK (((status)::text = ANY (ARRAY[('succeeded'::character varying)::text, ('failed'::character varying)::text])))
);

-- Name: TABLE job_runs; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.job_runs IS '后台任务执行记录';

-- Name: COLUMN job_runs.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.job_runs.id IS '主键（UUID）';

-- Name: COLUMN job_runs.name; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.job_runs.name IS '任务名';

-- Name: COLUMN job_runs.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.job_runs.status IS '状态：running/success/failed';

-- Name: COLUMN job_runs.detail; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.job_runs.detail IS '执行详情';

-- Name: COLUMN job_runs.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.job_runs.created_at IS '创建时间（UTC）';

-- Name: login_devices; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.login_devices (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    user_agent text DEFAULT ''::text NOT NULL,
    ip character varying(64) DEFAULT ''::character varying NOT NULL,
    last_seen_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: TABLE login_devices; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.login_devices IS '登录设备记录：最近登录的 UA 与 IP';

-- Name: COLUMN login_devices.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.login_devices.id IS '主键（UUID）';

-- Name: COLUMN login_devices.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.login_devices.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN login_devices.ip; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.login_devices.ip IS '登录 IP';

-- Name: COLUMN login_devices.last_seen_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.login_devices.last_seen_at IS '最近活跃时间';

-- Name: COLUMN login_devices.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.login_devices.created_at IS '创建时间（UTC）';

-- Name: mfa_challenges; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.mfa_challenges (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    consumed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_mfa_challenge_token_hash_len CHECK ((char_length((token_hash)::text) = 64))
);

-- Name: TABLE mfa_challenges; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.mfa_challenges IS 'MFA 二次验证挑战（TOTP 流程临时凭证）';

-- Name: COLUMN mfa_challenges.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.mfa_challenges.id IS '主键（UUID）';

-- Name: COLUMN mfa_challenges.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.mfa_challenges.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN mfa_challenges.token_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.mfa_challenges.token_hash IS '令牌哈希（不存明文）';

-- Name: COLUMN mfa_challenges.expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.mfa_challenges.expires_at IS '过期时间（UTC）';

-- Name: COLUMN mfa_challenges.attempt_count; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.mfa_challenges.attempt_count IS '已尝试验证次数（防爆破）';

-- Name: COLUMN mfa_challenges.consumed_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.mfa_challenges.consumed_at IS '核销时间，NULL 表示未使用';

-- Name: COLUMN mfa_challenges.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.mfa_challenges.created_at IS '创建时间（UTC）';

-- Name: model_catalog; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.model_catalog (
    id uuid NOT NULL,
    provider_id uuid NOT NULL,
    public_name character varying(128) NOT NULL,
    display_name character varying(128) NOT NULL,
    upstream_name character varying(128) NOT NULL,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    supports_stream boolean,
    supports_tools boolean,
    supports_vision boolean,
    supports_embeddings boolean,
    supports_images boolean,
    context_window integer,
    max_output integer,
    upstream_input_price numeric(24,8),
    upstream_output_price numeric(24,8),
    upstream_schedule_rules jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_model_catalog_status CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('published'::character varying)::text, ('disabled'::character varying)::text])))
);

-- Name: TABLE model_catalog; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.model_catalog IS '模型目录：对外模型定义、能力位、上游建议价与时段规则';

-- Name: COLUMN model_catalog.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.id IS '主键（UUID）';

-- Name: COLUMN model_catalog.provider_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.provider_id IS '供应商 ID → providers.id';

-- Name: COLUMN model_catalog.public_name; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.public_name IS '对外模型名（API 调用时使用）';

-- Name: COLUMN model_catalog.display_name; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.display_name IS '展示名';

-- Name: COLUMN model_catalog.upstream_name; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.upstream_name IS '上游真实模型 ID';

-- Name: COLUMN model_catalog.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.status IS '状态：pending/published/disabled';

-- Name: COLUMN model_catalog.supports_stream; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.supports_stream IS '是否支持流式输出';

-- Name: COLUMN model_catalog.supports_tools; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.supports_tools IS '是否支持工具调用';

-- Name: COLUMN model_catalog.supports_vision; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.supports_vision IS '是否支持图像输入';

-- Name: COLUMN model_catalog.supports_embeddings; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.supports_embeddings IS '是否支持向量嵌入';

-- Name: COLUMN model_catalog.supports_images; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.supports_images IS '是否支持图像生成';

-- Name: COLUMN model_catalog.context_window; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.context_window IS '上下文窗口（token 数）';

-- Name: COLUMN model_catalog.max_output; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.max_output IS '最大输出 token 数';

-- Name: COLUMN model_catalog.upstream_input_price; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.upstream_input_price IS '上游建议输入价（USD/token）';

-- Name: COLUMN model_catalog.upstream_output_price; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.upstream_output_price IS '上游建议输出价（USD/token）';

-- Name: COLUMN model_catalog.upstream_schedule_rules; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.upstream_schedule_rules IS '上游时段定价规则原文（JSONB）';

-- Name: COLUMN model_catalog.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_catalog.created_at IS '创建时间（UTC）';

-- Name: model_deployments; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.model_deployments (
    id uuid NOT NULL,
    model_id uuid NOT NULL,
    provider_id uuid NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_model_deployments_status CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('disabled'::character varying)::text])))
);

-- Name: TABLE model_deployments; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.model_deployments IS '模型部署：模型与供应商的多对多发布关系';

-- Name: COLUMN model_deployments.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_deployments.id IS '主键（UUID）';

-- Name: COLUMN model_deployments.model_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_deployments.model_id IS '模型 ID → model_catalog.id';

-- Name: COLUMN model_deployments.provider_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_deployments.provider_id IS '供应商 ID → providers.id';

-- Name: COLUMN model_deployments.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_deployments.status IS '状态：active/disabled';

-- Name: COLUMN model_deployments.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_deployments.created_at IS '创建时间（UTC）';

-- Name: model_prices; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.model_prices (
    id uuid NOT NULL,
    pricing_version_id uuid NOT NULL,
    meter character varying(32) NOT NULL,
    unit_price numeric(24,8) NOT NULL,
    cost_price numeric(24,8) NOT NULL,
    min_billable_units integer DEFAULT 0 NOT NULL,
    tier_min_tokens integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_model_prices_meter CHECK (((meter)::text = ANY (ARRAY[('input_token'::character varying)::text, ('output_token'::character varying)::text, ('cached_input_token'::character varying)::text, ('image'::character varying)::text]))),
    CONSTRAINT ck_model_prices_min_units CHECK ((min_billable_units >= 0)),
    CONSTRAINT ck_model_prices_nonnegative CHECK (((unit_price >= (0)::numeric) AND (cost_price >= (0)::numeric))),
    CONSTRAINT ck_model_prices_tier_min CHECK ((tier_min_tokens >= 0))
);

-- Name: TABLE model_prices; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.model_prices IS '模型价格明细：按 meter 与阶梯档位定义单价';

-- Name: COLUMN model_prices.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_prices.id IS '主键（UUID）';

-- Name: COLUMN model_prices.pricing_version_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_prices.pricing_version_id IS '所属定价版本 ID';

-- Name: COLUMN model_prices.meter; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_prices.meter IS '计费维度：input_token/output_token/cached_input_token/per_request';

-- Name: COLUMN model_prices.unit_price; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_prices.unit_price IS '售价单价（每 token 或每次，USD）';

-- Name: COLUMN model_prices.cost_price; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_prices.cost_price IS '成本单价（毛利分析用）';

-- Name: COLUMN model_prices.min_billable_units; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_prices.min_billable_units IS '最小计费单位数';

-- Name: COLUMN model_prices.tier_min_tokens; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_prices.tier_min_tokens IS '阶梯档位下限（输入 token 数 ≥ 此值命中该档）';

-- Name: model_sync_jobs; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.model_sync_jobs (
    id uuid NOT NULL,
    provider_id uuid NOT NULL,
    status character varying(16) NOT NULL,
    discovered_count integer DEFAULT 0 NOT NULL,
    error character varying(256),
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT ck_model_sync_jobs_status CHECK (((status)::text = ANY (ARRAY[('running'::character varying)::text, ('succeeded'::character varying)::text, ('failed'::character varying)::text])))
);

-- Name: TABLE model_sync_jobs; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.model_sync_jobs IS '模型同步任务：从上游拉取模型列表的执行记录';

-- Name: COLUMN model_sync_jobs.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_sync_jobs.id IS '主键（UUID）';

-- Name: COLUMN model_sync_jobs.provider_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_sync_jobs.provider_id IS '供应商 ID → providers.id';

-- Name: COLUMN model_sync_jobs.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_sync_jobs.status IS '状态';

-- Name: COLUMN model_sync_jobs.discovered_count; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_sync_jobs.discovered_count IS '本次发现的模型数量';

-- Name: COLUMN model_sync_jobs.error; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_sync_jobs.error IS '错误信息';

-- Name: COLUMN model_sync_jobs.started_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_sync_jobs.started_at IS '开始时间';

-- Name: COLUMN model_sync_jobs.finished_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_sync_jobs.finished_at IS '结束时间';

-- Name: model_test_runs; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.model_test_runs (
    id uuid NOT NULL,
    provider_id uuid NOT NULL,
    mode character varying(32) NOT NULL,
    ok boolean NOT NULL,
    http_status integer,
    latency_ms integer,
    usage_present boolean DEFAULT false NOT NULL,
    error character varying(256),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: TABLE model_test_runs; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.model_test_runs IS '模型可用性测试记录';

-- Name: COLUMN model_test_runs.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_test_runs.id IS '主键（UUID）';

-- Name: COLUMN model_test_runs.provider_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_test_runs.provider_id IS '供应商 ID → providers.id';

-- Name: COLUMN model_test_runs.mode; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_test_runs.mode IS '测试模式：chat/embedding 等';

-- Name: COLUMN model_test_runs.ok; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_test_runs.ok IS '是否成功';

-- Name: COLUMN model_test_runs.http_status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_test_runs.http_status IS 'HTTP 状态码';

-- Name: COLUMN model_test_runs.latency_ms; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_test_runs.latency_ms IS '耗时（毫秒）';

-- Name: COLUMN model_test_runs.usage_present; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_test_runs.usage_present IS '上游是否返回 usage';

-- Name: COLUMN model_test_runs.error; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_test_runs.error IS '错误信息';

-- Name: COLUMN model_test_runs.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.model_test_runs.created_at IS '创建时间（UTC）';

-- Name: notification_preferences; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.notification_preferences (
    user_id uuid NOT NULL,
    balance_alerts_enabled boolean DEFAULT true NOT NULL,
    warn_high numeric(24,8) DEFAULT 10 NOT NULL,
    warn_low numeric(24,8) DEFAULT 2 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: TABLE notification_preferences; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.notification_preferences IS '通知偏好：余额预警阈值等';

-- Name: COLUMN notification_preferences.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notification_preferences.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN notification_preferences.balance_alerts_enabled; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notification_preferences.balance_alerts_enabled IS '是否开启余额预警';

-- Name: COLUMN notification_preferences.warn_high; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notification_preferences.warn_high IS '高阈值';

-- Name: COLUMN notification_preferences.warn_low; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notification_preferences.warn_low IS '低阈值';

-- Name: COLUMN notification_preferences.updated_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notification_preferences.updated_at IS '更新时间（UTC）';

-- Name: notifications; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.notifications (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    title character varying(160) NOT NULL,
    body text DEFAULT ''::text NOT NULL,
    related_id uuid,
    dedupe_key character varying(160) NOT NULL,
    read_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_notifications_kind CHECK (((kind)::text = ANY (ARRAY[('security'::character varying)::text, ('key_expiry'::character varying)::text, ('balance'::character varying)::text])))
);

-- Name: TABLE notifications; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.notifications IS '站内通知';

-- Name: COLUMN notifications.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notifications.id IS '主键（UUID）';

-- Name: COLUMN notifications.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notifications.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN notifications.kind; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notifications.kind IS '通知类型';

-- Name: COLUMN notifications.title; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notifications.title IS '标题';

-- Name: COLUMN notifications.body; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notifications.body IS '正文';

-- Name: COLUMN notifications.related_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notifications.related_id IS '关联对象 ID';

-- Name: COLUMN notifications.dedupe_key; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notifications.dedupe_key IS '去重键（防止重复通知）';

-- Name: COLUMN notifications.read_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notifications.read_at IS '阅读时间，NULL 表示未读';

-- Name: COLUMN notifications.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.notifications.created_at IS '创建时间（UTC）';

-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.password_reset_tokens (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    consumed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_password_reset_token_hash_len CHECK ((char_length((token_hash)::text) = 64))
);

-- Name: TABLE password_reset_tokens; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.password_reset_tokens IS '密码重置令牌（哈希存储，一次性）';

-- Name: COLUMN password_reset_tokens.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.password_reset_tokens.id IS '主键（UUID）';

-- Name: COLUMN password_reset_tokens.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.password_reset_tokens.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN password_reset_tokens.token_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.password_reset_tokens.token_hash IS '令牌哈希（不存明文）';

-- Name: COLUMN password_reset_tokens.expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.password_reset_tokens.expires_at IS '过期时间（UTC）';

-- Name: COLUMN password_reset_tokens.attempt_count; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.password_reset_tokens.attempt_count IS '已尝试验证次数（防爆破）';

-- Name: COLUMN password_reset_tokens.consumed_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.password_reset_tokens.consumed_at IS '核销时间，NULL 表示未使用';

-- Name: COLUMN password_reset_tokens.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.password_reset_tokens.created_at IS '创建时间（UTC）';

-- Name: payment_events; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.payment_events (
    id uuid NOT NULL,
    order_id uuid,
    source character varying(32) NOT NULL,
    payload_redacted text NOT NULL,
    signature_ok boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);

-- Name: TABLE payment_events; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.payment_events IS '支付回调事件：网关通知原文（脱敏）与验签结果';

-- Name: COLUMN payment_events.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_events.id IS '主键（UUID）';

-- Name: COLUMN payment_events.order_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_events.order_id IS '所属订单 ID → payment_orders.id';

-- Name: COLUMN payment_events.source; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_events.source IS '事件来源（webhook 渠道）';

-- Name: COLUMN payment_events.payload_redacted; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_events.payload_redacted IS '回调报文（已脱敏）';

-- Name: COLUMN payment_events.signature_ok; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_events.signature_ok IS '签名校验是否通过';

-- Name: COLUMN payment_events.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_events.created_at IS '创建时间（UTC）';

-- Name: payment_orders; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.payment_orders (
    id uuid NOT NULL,
    order_no character varying(40) NOT NULL,
    user_id uuid NOT NULL,
    product_id uuid,
    channel character varying(16) NOT NULL,
    amount numeric(24,8) NOT NULL,
    currency character varying(8) NOT NULL,
    bonus_amount numeric(24,8) DEFAULT 0 NOT NULL,
    credited_amount numeric(24,8),
    crypto_amount numeric(24,8),
    crypto_currency character varying(8),
    network character varying(16),
    pay_address character varying(128),
    payer_address character varying(128),
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    locked_rate numeric(24,8),
    rate_source character varying(64),
    locked_at timestamp with time zone,
    expires_at timestamp with time zone NOT NULL,
    provider_ref character varying(128),
    checkout_url character varying(512),
    provider_snapshot text,
    tx_hash character varying(128),
    confirmations integer DEFAULT 0 NOT NULL,
    actual_amount numeric(24,8),
    risk_status character varying(16) DEFAULT 'clear'::character varying NOT NULL,
    reconcile_status character varying(16) DEFAULT 'unchecked'::character varying NOT NULL,
    idempotency_key character varying(80) NOT NULL,
    request_hash character varying(64) NOT NULL,
    paid_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_payment_orders_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_payment_orders_channel CHECK (((channel)::text = ANY (ARRAY[('mock'::character varying)::text, ('stripe'::character varying)::text, ('usdt'::character varying)::text, ('wechat'::character varying)::text, ('alipay'::character varying)::text]))),
    CONSTRAINT ck_payment_orders_reconcile CHECK (((reconcile_status)::text = ANY (ARRAY[('unchecked'::character varying)::text, ('matched'::character varying)::text, ('disputed'::character varying)::text]))),
    CONSTRAINT ck_payment_orders_risk CHECK (((risk_status)::text = ANY (ARRAY[('clear'::character varying)::text, ('sanctioned'::character varying)::text, ('large_review'::character varying)::text]))),
    CONSTRAINT ck_payment_orders_status CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('confirming'::character varying)::text, ('completed'::character varying)::text, ('expired'::character varying)::text, ('underpaid'::character varying)::text, ('overpaid'::character varying)::text, ('closed'::character varying)::text, ('refunded'::character varying)::text])))
);

-- Name: TABLE payment_orders; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.payment_orders IS '支付订单：法币/加密货币充值单及其对账状态';

-- Name: COLUMN payment_orders.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.id IS '主键（UUID）';

-- Name: COLUMN payment_orders.order_no; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.order_no IS '订单号（业务唯一）';

-- Name: COLUMN payment_orders.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN payment_orders.product_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.product_id IS '充值套餐 ID → recharge_products.id';

-- Name: COLUMN payment_orders.channel; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.channel IS '支付渠道：stripe/crypto_manual 等';

-- Name: COLUMN payment_orders.amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.amount IS '金额';

-- Name: COLUMN payment_orders.currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.currency IS '币种（ISO 4217，如 USD/CNY）';

-- Name: COLUMN payment_orders.bonus_amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.bonus_amount IS '赠送金额';

-- Name: COLUMN payment_orders.credited_amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.credited_amount IS '实际入账金额';

-- Name: COLUMN payment_orders.crypto_amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.crypto_amount IS '加密货币数量';

-- Name: COLUMN payment_orders.crypto_currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.crypto_currency IS '加密货币币种（如 USDT）';

-- Name: COLUMN payment_orders.network; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.network IS '区块链网络（如 TRC20/ERC20）';

-- Name: COLUMN payment_orders.pay_address; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.pay_address IS '收款地址';

-- Name: COLUMN payment_orders.payer_address; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.payer_address IS '付款地址（链上识别）';

-- Name: COLUMN payment_orders.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.status IS '状态：pending/paid/expired/failed';

-- Name: COLUMN payment_orders.locked_rate; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.locked_rate IS '锁仓汇率';

-- Name: COLUMN payment_orders.rate_source; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.rate_source IS '汇率来源';

-- Name: COLUMN payment_orders.locked_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.locked_at IS '汇率锁定时间';

-- Name: COLUMN payment_orders.expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.expires_at IS '过期时间（UTC）';

-- Name: COLUMN payment_orders.provider_ref; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.provider_ref IS '支付网关侧订单号';

-- Name: COLUMN payment_orders.tx_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.tx_hash IS '链上交易哈希';

-- Name: COLUMN payment_orders.confirmations; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.confirmations IS '区块确认数';

-- Name: COLUMN payment_orders.actual_amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.actual_amount IS '实际到账金额';

-- Name: COLUMN payment_orders.risk_status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.risk_status IS '风控状态';

-- Name: COLUMN payment_orders.reconcile_status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.reconcile_status IS '对账状态';

-- Name: COLUMN payment_orders.idempotency_key; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.idempotency_key IS '幂等键';

-- Name: COLUMN payment_orders.request_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.request_hash IS '请求体哈希（幂等校验）';

-- Name: COLUMN payment_orders.paid_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.paid_at IS '支付完成时间';

-- Name: COLUMN payment_orders.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.created_at IS '创建时间（UTC）';

-- Name: COLUMN payment_orders.updated_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.payment_orders.updated_at IS '更新时间（UTC）';

-- Name: permissions; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.permissions (
    id uuid NOT NULL,
    code character varying(128) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: TABLE permissions; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.permissions IS '权限点定义：后台操作的最小授权单元';

-- Name: COLUMN permissions.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.permissions.id IS '主键（UUID）';

-- Name: COLUMN permissions.code; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.permissions.code IS '权限代码（如 refund:execute）';

-- Name: COLUMN permissions.description; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.permissions.description IS '权限说明';

-- Name: COLUMN permissions.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.permissions.created_at IS '创建时间（UTC）';

-- Name: pricing_versions; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.pricing_versions (
    id uuid NOT NULL,
    model_id uuid NOT NULL,
    version integer NOT NULL,
    currency character varying(8) NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    schedule_rules jsonb,
    CONSTRAINT ck_pricing_versions_version CHECK ((version >= 1))
);

-- Name: TABLE pricing_versions; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.pricing_versions IS '定价版本：按模型维度发布，含时段定价规则';

-- Name: COLUMN pricing_versions.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.pricing_versions.id IS '主键（UUID）';

-- Name: COLUMN pricing_versions.model_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.pricing_versions.model_id IS '模型 ID → model_catalog.id';

-- Name: COLUMN pricing_versions.version; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.pricing_versions.version IS '版本号（同一模型递增）';

-- Name: COLUMN pricing_versions.currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.pricing_versions.currency IS '币种（ISO 4217，如 USD/CNY）';

-- Name: COLUMN pricing_versions.effective_from; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.pricing_versions.effective_from IS '生效时间';

-- Name: COLUMN pricing_versions.effective_to; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.pricing_versions.effective_to IS '失效时间，NULL 表示当前生效';

-- Name: COLUMN pricing_versions.created_by; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.pricing_versions.created_by IS '创建人用户 ID';

-- Name: COLUMN pricing_versions.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.pricing_versions.created_at IS '创建时间（UTC）';

-- Name: COLUMN pricing_versions.schedule_rules; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.pricing_versions.schedule_rules IS '时段定价规则（JSONB，UTC 时段 + 节假日排除）';

-- Name: provider_credentials; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.provider_credentials (
    id uuid NOT NULL,
    provider_id uuid NOT NULL,
    label character varying(128) NOT NULL,
    secret_ciphertext text NOT NULL,
    secret_hint character varying(32) NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    last_used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_provider_credentials_status CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('revoked'::character varying)::text])))
);

-- Name: TABLE provider_credentials; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.provider_credentials IS '上游供应商密钥（密文存储）';

-- Name: COLUMN provider_credentials.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.provider_credentials.id IS '主键（UUID）';

-- Name: COLUMN provider_credentials.provider_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.provider_credentials.provider_id IS '供应商 ID → providers.id';

-- Name: COLUMN provider_credentials.label; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.provider_credentials.label IS '密钥备注名';

-- Name: COLUMN provider_credentials.secret_ciphertext; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.provider_credentials.secret_ciphertext IS '密钥密文（加密存储）';

-- Name: COLUMN provider_credentials.secret_hint; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.provider_credentials.secret_hint IS '密钥提示（如 sk-...1234）';

-- Name: COLUMN provider_credentials.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.provider_credentials.status IS '状态';

-- Name: COLUMN provider_credentials.last_used_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.provider_credentials.last_used_at IS '最近使用时间';

-- Name: COLUMN provider_credentials.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.provider_credentials.created_at IS '创建时间（UTC）';

-- Name: providers; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.providers (
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    kind character varying(32) NOT NULL,
    base_url text NOT NULL,
    protocol character varying(32) DEFAULT 'openai'::character varying NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    timeout_seconds integer DEFAULT 60 NOT NULL,
    priority integer DEFAULT 100 NOT NULL,
    weight integer DEFAULT 1 NOT NULL,
    max_concurrency integer,
    rpm_limit integer,
    tpm_limit integer,
    last_error character varying(256),
    last_latency_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_providers_kind CHECK (((kind)::text = ANY (ARRAY[('openai'::character varying)::text, ('anthropic'::character varying)::text, ('cloud'::character varying)::text, ('self_hosted'::character varying)::text, ('ollama'::character varying)::text, ('compatible'::character varying)::text]))),
    CONSTRAINT ck_providers_status CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('disabled'::character varying)::text, ('deleted'::character varying)::text])))
);

-- Name: TABLE providers; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.providers IS '上游供应商：协议、限速、并发、健康状态';

-- Name: COLUMN providers.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.id IS '主键（UUID）';

-- Name: COLUMN providers.name; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.name IS '供应商标识（小写，如 deepseek/openrouter）';

-- Name: COLUMN providers.kind; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.kind IS '类型：official/compatible/ollama 等';

-- Name: COLUMN providers.base_url; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.base_url IS '上游 API 基础地址';

-- Name: COLUMN providers.protocol; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.protocol IS '协议方言：openai/anthropic 等';

-- Name: COLUMN providers.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.status IS '状态：active/disabled';

-- Name: COLUMN providers.timeout_seconds; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.timeout_seconds IS '请求超时（秒）';

-- Name: COLUMN providers.priority; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.priority IS '优先级（越小越优先）';

-- Name: COLUMN providers.weight; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.weight IS '负载均衡权重';

-- Name: COLUMN providers.max_concurrency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.max_concurrency IS '最大并发数';

-- Name: COLUMN providers.rpm_limit; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.rpm_limit IS '每分钟请求数上限';

-- Name: COLUMN providers.tpm_limit; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.tpm_limit IS '每分钟 token 数上限';

-- Name: COLUMN providers.last_error; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.last_error IS '最近一次错误信息';

-- Name: COLUMN providers.last_latency_ms; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.last_latency_ms IS '最近一次调用耗时（毫秒）';

-- Name: COLUMN providers.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.created_at IS '创建时间（UTC）';

-- Name: COLUMN providers.updated_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.providers.updated_at IS '更新时间（UTC）';

-- Name: recharge_products; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.recharge_products (
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    amount numeric(24,8) NOT NULL,
    currency character varying(8) NOT NULL,
    bonus_amount numeric(24,8) DEFAULT 0 NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    allowed_models text DEFAULT '[]'::text NOT NULL,
    CONSTRAINT ck_recharge_products_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_recharge_products_bonus CHECK ((bonus_amount >= (0)::numeric))
);

-- Name: TABLE recharge_products; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.recharge_products IS '充值套餐：面额、赠送金额、排序';

-- Name: COLUMN recharge_products.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.recharge_products.id IS '主键（UUID）';

-- Name: COLUMN recharge_products.name; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.recharge_products.name IS '套餐名称';

-- Name: COLUMN recharge_products.amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.recharge_products.amount IS '金额';

-- Name: COLUMN recharge_products.currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.recharge_products.currency IS '币种（ISO 4217，如 USD/CNY）';

-- Name: COLUMN recharge_products.bonus_amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.recharge_products.bonus_amount IS '赠送金额';

-- Name: COLUMN recharge_products.enabled; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.recharge_products.enabled IS '是否上架';

-- Name: COLUMN recharge_products.sort_order; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.recharge_products.sort_order IS '展示排序（越小越前）';

-- Name: COLUMN recharge_products.deleted_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.recharge_products.deleted_at IS '软删除时间，NULL 表示未删除';

-- Name: COLUMN recharge_products.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.recharge_products.created_at IS '创建时间（UTC）';

-- Name: COLUMN recharge_products.allowed_models; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.recharge_products.allowed_models IS '套餐默认可用模型（JSON 数组，空数组=不限）';

-- Name: refund_orders; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.refund_orders (
    id uuid NOT NULL,
    order_id uuid NOT NULL,
    amount numeric(24,8) NOT NULL,
    currency character varying(8) NOT NULL,
    status character varying(16) DEFAULT 'requested'::character varying NOT NULL,
    requested_by uuid NOT NULL,
    reviewed_by uuid,
    executed_by uuid,
    destination_address character varying(128) DEFAULT ''::character varying NOT NULL,
    tx_hash character varying(128),
    reason character varying(256) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    reviewed_at timestamp with time zone,
    executed_at timestamp with time zone,
    CONSTRAINT ck_refund_orders_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_refund_orders_executor CHECK (((executed_by IS NULL) OR (executed_by <> requested_by))),
    CONSTRAINT ck_refund_orders_reviewer CHECK (((reviewed_by IS NULL) OR (reviewed_by <> requested_by))),
    CONSTRAINT ck_refund_orders_status CHECK (((status)::text = ANY (ARRAY[('requested'::character varying)::text, ('reviewed'::character varying)::text, ('executed'::character varying)::text, ('rejected'::character varying)::text])))
);

-- Name: TABLE refund_orders; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.refund_orders IS '退款单：申请、审核、执行三段式流程';

-- Name: COLUMN refund_orders.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.id IS '主键（UUID）';

-- Name: COLUMN refund_orders.order_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.order_id IS '原支付订单 ID → payment_orders.id';

-- Name: COLUMN refund_orders.amount; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.amount IS '金额';

-- Name: COLUMN refund_orders.currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.currency IS '币种（ISO 4217，如 USD/CNY）';

-- Name: COLUMN refund_orders.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.status IS '状态：requested/approved/executed/rejected';

-- Name: COLUMN refund_orders.requested_by; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.requested_by IS '申请人用户 ID';

-- Name: COLUMN refund_orders.reviewed_by; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.reviewed_by IS '审核人用户 ID';

-- Name: COLUMN refund_orders.executed_by; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.executed_by IS '执行人用户 ID';

-- Name: COLUMN refund_orders.destination_address; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.destination_address IS '退款目标地址（加密货币）';

-- Name: COLUMN refund_orders.tx_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.tx_hash IS '退款交易哈希';

-- Name: COLUMN refund_orders.reason; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.reason IS '退款原因';

-- Name: COLUMN refund_orders.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.created_at IS '创建时间（UTC）';

-- Name: COLUMN refund_orders.reviewed_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.reviewed_at IS '审核时间';

-- Name: COLUMN refund_orders.executed_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.refund_orders.executed_at IS '执行时间';

-- Name: role_permissions; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.role_permissions (
    role_id uuid NOT NULL,
    permission_id uuid NOT NULL
);

-- Name: TABLE role_permissions; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.role_permissions IS '角色-权限映射（多对多）';

-- Name: COLUMN role_permissions.role_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.role_permissions.role_id IS '角色 ID → roles.id';

-- Name: COLUMN role_permissions.permission_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.role_permissions.permission_id IS '权限 ID → permissions.id';

-- Name: roles; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.roles (
    id uuid NOT NULL,
    code character varying(64) NOT NULL,
    name character varying(128) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    is_system boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: TABLE roles; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.roles IS '角色定义：user/support/finance/operator/model_ops/admin/superadmin';

-- Name: COLUMN roles.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.roles.id IS '主键（UUID）';

-- Name: COLUMN roles.code; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.roles.code IS '角色代码（程序引用，如 superadmin）';

-- Name: COLUMN roles.name; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.roles.name IS '角色显示名';

-- Name: COLUMN roles.is_system; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.roles.is_system IS '是否系统内置角色（禁止删除）';

-- Name: COLUMN roles.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.roles.created_at IS '创建时间（UTC）';

-- Name: sanctioned_address_blocks; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.sanctioned_address_blocks (
    id uuid NOT NULL,
    address character varying(128) NOT NULL,
    network character varying(16) NOT NULL,
    source character varying(64) NOT NULL,
    reason character varying(256) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone NOT NULL
);

-- Name: TABLE sanctioned_address_blocks; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.sanctioned_address_blocks IS '制裁地址黑名单：加密货币收款风控';

-- Name: COLUMN sanctioned_address_blocks.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sanctioned_address_blocks.id IS '主键（UUID）';

-- Name: COLUMN sanctioned_address_blocks.address; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sanctioned_address_blocks.address IS '黑名单地址';

-- Name: COLUMN sanctioned_address_blocks.network; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sanctioned_address_blocks.network IS '区块链网络';

-- Name: COLUMN sanctioned_address_blocks.source; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sanctioned_address_blocks.source IS '名单来源';

-- Name: COLUMN sanctioned_address_blocks.reason; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sanctioned_address_blocks.reason IS '封禁原因';

-- Name: COLUMN sanctioned_address_blocks.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sanctioned_address_blocks.created_at IS '创建时间（UTC）';

-- Name: sessions; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    absolute_expires_at timestamp with time zone NOT NULL,
    idle_expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    created_ip character varying(64),
    last_seen_ip character varying(64),
    user_agent text,
    CONSTRAINT ck_sessions_token_hash_len CHECK ((char_length((token_hash)::text) = 64))
);

-- Name: TABLE sessions; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.sessions IS '登录会话：令牌哈希、过期与撤销';

-- Name: COLUMN sessions.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.id IS '主键（UUID）';

-- Name: COLUMN sessions.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN sessions.token_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.token_hash IS '令牌哈希（不存明文）';

-- Name: COLUMN sessions.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.created_at IS '创建时间（UTC）';

-- Name: COLUMN sessions.last_seen_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.last_seen_at IS '最近活跃时间';

-- Name: COLUMN sessions.absolute_expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.absolute_expires_at IS '绝对过期时间（硬上限）';

-- Name: COLUMN sessions.idle_expires_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.idle_expires_at IS '空闲过期时间（滑动窗口）';

-- Name: COLUMN sessions.revoked_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.revoked_at IS '撤销时间，NULL 表示有效';

-- Name: COLUMN sessions.created_ip; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.created_ip IS '创建会话时 IP';

-- Name: COLUMN sessions.last_seen_ip; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.last_seen_ip IS '最近活跃 IP';

-- Name: COLUMN sessions.user_agent; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.sessions.user_agent IS '客户端 User-Agent';

-- Name: ticket_messages; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.ticket_messages (
    id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    author_id uuid NOT NULL,
    body text NOT NULL,
    created_at timestamp with time zone NOT NULL
);

-- Name: TABLE ticket_messages; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.ticket_messages IS '工单消息';

-- Name: COLUMN ticket_messages.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.ticket_messages.id IS '主键（UUID）';

-- Name: COLUMN ticket_messages.ticket_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.ticket_messages.ticket_id IS '所属工单 ID → tickets.id';

-- Name: COLUMN ticket_messages.author_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.ticket_messages.author_id IS '发言人用户 ID';

-- Name: COLUMN ticket_messages.body; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.ticket_messages.body IS '消息内容';

-- Name: COLUMN ticket_messages.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.ticket_messages.created_at IS '创建时间（UTC）';

-- Name: tickets; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.tickets (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    category character varying(16) NOT NULL,
    subject character varying(160) NOT NULL,
    status character varying(16) DEFAULT 'open'::character varying NOT NULL,
    priority character varying(16) DEFAULT 'normal'::character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_tickets_category CHECK (((category)::text = ANY (ARRAY[('billing'::character varying)::text, ('technical'::character varying)::text, ('refund'::character varying)::text, ('chain'::character varying)::text, ('other'::character varying)::text]))),
    CONSTRAINT ck_tickets_priority CHECK (((priority)::text = ANY (ARRAY[('low'::character varying)::text, ('normal'::character varying)::text, ('high'::character varying)::text]))),
    CONSTRAINT ck_tickets_status CHECK (((status)::text = ANY (ARRAY[('open'::character varying)::text, ('pending'::character varying)::text, ('resolved'::character varying)::text, ('closed'::character varying)::text])))
);

-- Name: TABLE tickets; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.tickets IS '工单';

-- Name: COLUMN tickets.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.tickets.id IS '主键（UUID）';

-- Name: COLUMN tickets.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.tickets.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN tickets.category; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.tickets.category IS '工单分类';

-- Name: COLUMN tickets.subject; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.tickets.subject IS '工单主题';

-- Name: COLUMN tickets.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.tickets.status IS '状态';

-- Name: COLUMN tickets.priority; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.tickets.priority IS '优先级：low/normal/high/urgent';

-- Name: COLUMN tickets.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.tickets.created_at IS '创建时间（UTC）';

-- Name: COLUMN tickets.updated_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.tickets.updated_at IS '更新时间（UTC）';

-- Name: totp_recovery_codes; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.totp_recovery_codes (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    code_hash character varying(64) NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_totp_recovery_code_hash_len CHECK ((char_length((code_hash)::text) = 64))
);

-- Name: TABLE totp_recovery_codes; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.totp_recovery_codes IS 'TOTP 备用恢复码（哈希存储，用后作废）';

-- Name: COLUMN totp_recovery_codes.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.totp_recovery_codes.id IS '主键（UUID）';

-- Name: COLUMN totp_recovery_codes.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.totp_recovery_codes.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN totp_recovery_codes.code_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.totp_recovery_codes.code_hash IS '恢复码哈希（不存明文）';

-- Name: COLUMN totp_recovery_codes.used_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.totp_recovery_codes.used_at IS '使用时间，NULL 表示未用';

-- Name: COLUMN totp_recovery_codes.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.totp_recovery_codes.created_at IS '创建时间（UTC）';

-- Name: usage_records; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.usage_records (
    id uuid NOT NULL,
    request_id character varying(64) NOT NULL,
    user_id uuid NOT NULL,
    api_key_id uuid,
    model_id character varying(128),
    started_at timestamp with time zone NOT NULL,
    ended_at timestamp with time zone,
    input_tokens integer DEFAULT 0 NOT NULL,
    output_tokens integer DEFAULT 0 NOT NULL,
    cached_tokens integer DEFAULT 0 NOT NULL,
    user_charge numeric(24,8),
    currency character varying(8) DEFAULT 'USD'::character varying NOT NULL,
    http_status integer,
    latency_ms integer,
    first_token_ms integer,
    is_stream boolean DEFAULT false NOT NULL,
    settlement_status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    pricing_version_id uuid,
    unit_price_snapshot text,
    provider_cost numeric(24,8),
    usage_source character varying(16),
    finish_reason character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_usage_records_settlement CHECK (((settlement_status)::text = ANY (ARRAY[('pending'::character varying)::text, ('settled'::character varying)::text, ('released'::character varying)::text, ('disputed'::character varying)::text])))
);

-- Name: TABLE usage_records; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.usage_records IS '用量记录：每次模型调用的 token 数、费用与结算状态';

-- Name: COLUMN usage_records.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.id IS '主键（UUID）';

-- Name: COLUMN usage_records.request_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.request_id IS '网关请求 ID（唯一）';

-- Name: COLUMN usage_records.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN usage_records.model_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.model_id IS '调用模型（model_catalog.public_name）';

-- Name: COLUMN usage_records.started_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.started_at IS '请求开始时间';

-- Name: COLUMN usage_records.ended_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.ended_at IS '请求结束时间';

-- Name: COLUMN usage_records.input_tokens; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.input_tokens IS '输入 token 数';

-- Name: COLUMN usage_records.output_tokens; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.output_tokens IS '输出 token 数';

-- Name: COLUMN usage_records.cached_tokens; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.cached_tokens IS '缓存命中 token 数（按缓存价计费）';

-- Name: COLUMN usage_records.user_charge; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.user_charge IS '用户实扣金额';

-- Name: COLUMN usage_records.currency; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.currency IS '币种（ISO 4217，如 USD/CNY）';

-- Name: COLUMN usage_records.http_status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.http_status IS '上游响应 HTTP 状态码';

-- Name: COLUMN usage_records.latency_ms; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.latency_ms IS '总耗时（毫秒）';

-- Name: COLUMN usage_records.first_token_ms; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.first_token_ms IS '首 token 耗时（毫秒，流式）';

-- Name: COLUMN usage_records.is_stream; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.is_stream IS '是否流式请求';

-- Name: COLUMN usage_records.settlement_status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.settlement_status IS '结算状态：settled/disputed/refunded';

-- Name: COLUMN usage_records.pricing_version_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.pricing_version_id IS '结算时使用的定价版本';

-- Name: COLUMN usage_records.unit_price_snapshot; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.unit_price_snapshot IS '单价快照（JSON，含时段命中信息）';

-- Name: COLUMN usage_records.provider_cost; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.provider_cost IS '上游成本（毛利分析用）';

-- Name: COLUMN usage_records.usage_source; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.usage_source IS '用量来源：reported（上游返回）/estimated（估算）';

-- Name: COLUMN usage_records.finish_reason; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.finish_reason IS '结束原因：stop/length/error 等';

-- Name: COLUMN usage_records.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_records.created_at IS '创建时间（UTC）';

-- Name: usage_settlements; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.usage_settlements (
    id uuid NOT NULL,
    usage_record_id uuid NOT NULL,
    status character varying(16) NOT NULL,
    hold_id uuid,
    ledger_entry_id uuid,
    settled_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_usage_settlements_status CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('settled'::character varying)::text, ('released'::character varying)::text, ('disputed'::character varying)::text])))
);

-- Name: TABLE usage_settlements; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.usage_settlements IS '用量结算：用量记录与账本条目/预扣的关联';

-- Name: COLUMN usage_settlements.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_settlements.id IS '主键（UUID）';

-- Name: COLUMN usage_settlements.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.usage_settlements.status IS '状态';

-- Name: user_profiles; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.user_profiles (
    user_id uuid NOT NULL,
    display_name character varying(128) DEFAULT ''::character varying NOT NULL,
    timezone character varying(64) DEFAULT 'UTC'::character varying NOT NULL,
    locale character varying(16) DEFAULT 'zh-CN'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: TABLE user_profiles; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.user_profiles IS '用户资料：显示名、时区、语言偏好';

-- Name: COLUMN user_profiles.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.user_profiles.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN user_profiles.display_name; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.user_profiles.display_name IS '显示名';

-- Name: COLUMN user_profiles.timezone; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.user_profiles.timezone IS '时区（IANA，如 Asia/Shanghai）';

-- Name: COLUMN user_profiles.locale; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.user_profiles.locale IS '语言（如 zh-CN）';

-- Name: COLUMN user_profiles.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.user_profiles.created_at IS '创建时间（UTC）';

-- Name: COLUMN user_profiles.updated_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.user_profiles.updated_at IS '更新时间（UTC）';

-- Name: user_roles; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.user_roles (
    user_id uuid NOT NULL,
    role_id uuid NOT NULL,
    granted_by uuid,
    granted_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: TABLE user_roles; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.user_roles IS '用户-角色映射（多对多）';

-- Name: COLUMN user_roles.user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.user_roles.user_id IS '所属用户 ID → users.id';

-- Name: COLUMN user_roles.role_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.user_roles.role_id IS '角色 ID → roles.id';

-- Name: COLUMN user_roles.granted_by; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.user_roles.granted_by IS '授权人用户 ID';

-- Name: COLUMN user_roles.granted_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.user_roles.granted_at IS '授权时间';

-- Name: users; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.users (
    id uuid NOT NULL,
    email character varying(320) NOT NULL,
    email_normalized character varying(320) NOT NULL,
    password_hash text NOT NULL,
    status character varying(32) DEFAULT 'pending_verification'::character varying NOT NULL,
    failed_login_count integer DEFAULT 0 NOT NULL,
    locked_until timestamp with time zone,
    totp_enabled boolean DEFAULT false NOT NULL,
    totp_secret_encrypted text,
    totp_last_step integer,
    terms_version character varying(64),
    terms_accepted_at timestamp with time zone,
    privacy_version character varying(64),
    privacy_accepted_at timestamp with time zone,
    register_ip character varying(64),
    register_user_agent text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    allowed_models text DEFAULT '[]'::text NOT NULL,
    CONSTRAINT ck_users_status CHECK (((status)::text = ANY (ARRAY[('pending_verification'::character varying)::text, ('active'::character varying)::text, ('frozen'::character varying)::text, ('deleted'::character varying)::text])))
);

-- Name: TABLE users; Type: COMMENT; Schema: public; Owner: -

COMMENT ON TABLE public.users IS '用户主表：账号、密码哈希、状态、登录安全与合规字段';

-- Name: COLUMN users.id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.id IS '主键（UUID）';

-- Name: COLUMN users.email; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.email IS '登录邮箱（原始输入）';

-- Name: COLUMN users.email_normalized; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.email_normalized IS '规范化邮箱（小写，唯一索引）';

-- Name: COLUMN users.password_hash; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.password_hash IS '密码哈希（Argon2id）';

-- Name: COLUMN users.status; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.status IS '账号状态：active/frozen/deleted';

-- Name: COLUMN users.failed_login_count; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.failed_login_count IS '连续登录失败次数（锁定计数）';

-- Name: COLUMN users.locked_until; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.locked_until IS '锁定截止时间，NULL 表示未锁定';

-- Name: COLUMN users.totp_enabled; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.totp_enabled IS '是否已启用 TOTP 二次验证';

-- Name: COLUMN users.totp_secret_encrypted; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.totp_secret_encrypted IS 'TOTP 密钥（加密存储）';

-- Name: COLUMN users.terms_version; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.terms_version IS '已同意的服务条款版本';

-- Name: COLUMN users.terms_accepted_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.terms_accepted_at IS '服务条款同意时间';

-- Name: COLUMN users.privacy_version; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.privacy_version IS '已同意的隐私政策版本';

-- Name: COLUMN users.privacy_accepted_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.privacy_accepted_at IS '隐私政策同意时间';

-- Name: COLUMN users.register_ip; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.register_ip IS '注册时 IP';

-- Name: COLUMN users.register_user_agent; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.register_user_agent IS '注册时 User-Agent';

-- Name: COLUMN users.created_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.created_at IS '创建时间（UTC）';

-- Name: COLUMN users.updated_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.updated_at IS '更新时间（UTC）';

-- Name: COLUMN users.deleted_at; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.deleted_at IS '软删除时间，NULL 表示未删除';

-- Name: COLUMN users.allowed_models; Type: COMMENT; Schema: public; Owner: -

COMMENT ON COLUMN public.users.allowed_models IS '账号级可用模型（JSON 数组，空数组=未显式配置，回退到套餐范围）';

-- Name: audit_chain_lock id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.audit_chain_lock ALTER COLUMN id SET DEFAULT nextval('public.audit_chain_lock_id_seq'::regclass);

-- Name: content_safety_settings id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.content_safety_settings ALTER COLUMN id SET DEFAULT nextval('public.content_safety_settings_id_seq'::regclass);

-- Name: account_balances account_balances_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.account_balances
    ADD CONSTRAINT account_balances_pkey PRIMARY KEY (user_id, currency);

-- Name: account_ledger account_ledger_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.account_ledger
    ADD CONSTRAINT account_ledger_pkey PRIMARY KEY (id);

-- Name: announcements announcements_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT announcements_pkey PRIMARY KEY (id);

-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);

-- Name: audit_chain_lock audit_chain_lock_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.audit_chain_lock
    ADD CONSTRAINT audit_chain_lock_pkey PRIMARY KEY (id);

-- Name: audit_events audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_pkey PRIMARY KEY (id);

-- Name: balance_holds balance_holds_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.balance_holds
    ADD CONSTRAINT balance_holds_pkey PRIMARY KEY (id);

-- Name: content_audit_records content_audit_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.content_audit_records
    ADD CONSTRAINT content_audit_records_pkey PRIMARY KEY (id);

-- Name: content_safety_settings content_safety_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.content_safety_settings
    ADD CONSTRAINT content_safety_settings_pkey PRIMARY KEY (id);

-- Name: coupon_redemptions coupon_redemptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.coupon_redemptions
    ADD CONSTRAINT coupon_redemptions_pkey PRIMARY KEY (id);

-- Name: coupons coupons_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.coupons
    ADD CONSTRAINT coupons_pkey PRIMARY KEY (id);

-- Name: crypto_deposit_intents crypto_deposit_intents_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.crypto_deposit_intents
    ADD CONSTRAINT crypto_deposit_intents_pkey PRIMARY KEY (id);

-- Name: email_change_tokens email_change_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.email_change_tokens
    ADD CONSTRAINT email_change_tokens_pkey PRIMARY KEY (id);

-- Name: email_verification_tokens email_verification_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.email_verification_tokens
    ADD CONSTRAINT email_verification_tokens_pkey PRIMARY KEY (id);

-- Name: endpoint_allowlist endpoint_allowlist_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.endpoint_allowlist
    ADD CONSTRAINT endpoint_allowlist_pkey PRIMARY KEY (id);

-- Name: exchange_rates exchange_rates_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.exchange_rates
    ADD CONSTRAINT exchange_rates_pkey PRIMARY KEY (id);

-- Name: idempotency_records idempotency_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.idempotency_records
    ADD CONSTRAINT idempotency_records_pkey PRIMARY KEY (id);

-- Name: invoice_requests invoice_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.invoice_requests
    ADD CONSTRAINT invoice_requests_pkey PRIMARY KEY (id);

-- Name: job_runs job_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.job_runs
    ADD CONSTRAINT job_runs_pkey PRIMARY KEY (id);

-- Name: login_devices login_devices_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.login_devices
    ADD CONSTRAINT login_devices_pkey PRIMARY KEY (id);

-- Name: mfa_challenges mfa_challenges_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.mfa_challenges
    ADD CONSTRAINT mfa_challenges_pkey PRIMARY KEY (id);

-- Name: model_catalog model_catalog_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_catalog
    ADD CONSTRAINT model_catalog_pkey PRIMARY KEY (id);

-- Name: model_deployments model_deployments_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_deployments
    ADD CONSTRAINT model_deployments_pkey PRIMARY KEY (id);

-- Name: model_prices model_prices_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_prices
    ADD CONSTRAINT model_prices_pkey PRIMARY KEY (id);

-- Name: model_sync_jobs model_sync_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_sync_jobs
    ADD CONSTRAINT model_sync_jobs_pkey PRIMARY KEY (id);

-- Name: model_test_runs model_test_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_test_runs
    ADD CONSTRAINT model_test_runs_pkey PRIMARY KEY (id);

-- Name: notification_preferences notification_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT notification_preferences_pkey PRIMARY KEY (user_id);

-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);

-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id);

-- Name: payment_events payment_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.payment_events
    ADD CONSTRAINT payment_events_pkey PRIMARY KEY (id);

-- Name: payment_orders payment_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.payment_orders
    ADD CONSTRAINT payment_orders_pkey PRIMARY KEY (id);

-- Name: permissions permissions_code_key; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_code_key UNIQUE (code);

-- Name: permissions permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (id);

-- Name: pricing_versions pricing_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.pricing_versions
    ADD CONSTRAINT pricing_versions_pkey PRIMARY KEY (id);

-- Name: provider_credentials provider_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.provider_credentials
    ADD CONSTRAINT provider_credentials_pkey PRIMARY KEY (id);

-- Name: providers providers_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_pkey PRIMARY KEY (id);

-- Name: recharge_products recharge_products_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.recharge_products
    ADD CONSTRAINT recharge_products_pkey PRIMARY KEY (id);

-- Name: refund_orders refund_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.refund_orders
    ADD CONSTRAINT refund_orders_pkey PRIMARY KEY (id);

-- Name: role_permissions role_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (role_id, permission_id);

-- Name: roles roles_code_key; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_code_key UNIQUE (code);

-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);

-- Name: sanctioned_address_blocks sanctioned_address_blocks_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.sanctioned_address_blocks
    ADD CONSTRAINT sanctioned_address_blocks_pkey PRIMARY KEY (id);

-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);

-- Name: ticket_messages ticket_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.ticket_messages
    ADD CONSTRAINT ticket_messages_pkey PRIMARY KEY (id);

-- Name: tickets tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_pkey PRIMARY KEY (id);

-- Name: totp_recovery_codes totp_recovery_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.totp_recovery_codes
    ADD CONSTRAINT totp_recovery_codes_pkey PRIMARY KEY (id);

-- Name: account_ledger uq_account_ledger_idempotency; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.account_ledger
    ADD CONSTRAINT uq_account_ledger_idempotency UNIQUE (idempotency_key);

-- Name: announcements uq_announcements_slug; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT uq_announcements_slug UNIQUE (slug);

-- Name: api_keys uq_api_keys_key_hash; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT uq_api_keys_key_hash UNIQUE (key_hash);

-- Name: audit_events uq_audit_events_content_hash; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT uq_audit_events_content_hash UNIQUE (content_hash);

-- Name: audit_events uq_audit_events_seq; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT uq_audit_events_seq UNIQUE (seq);

-- Name: balance_holds uq_balance_holds_idempotency; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.balance_holds
    ADD CONSTRAINT uq_balance_holds_idempotency UNIQUE (idempotency_key);

-- Name: balance_holds uq_balance_holds_request; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.balance_holds
    ADD CONSTRAINT uq_balance_holds_request UNIQUE (request_id);

-- Name: coupon_redemptions uq_coupon_redemptions_user; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.coupon_redemptions
    ADD CONSTRAINT uq_coupon_redemptions_user UNIQUE (coupon_id, user_id);

-- Name: coupons uq_coupons_code; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.coupons
    ADD CONSTRAINT uq_coupons_code UNIQUE (code);

-- Name: crypto_deposit_intents uq_crypto_deposit_intents_order; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.crypto_deposit_intents
    ADD CONSTRAINT uq_crypto_deposit_intents_order UNIQUE (order_id);

-- Name: email_change_tokens uq_email_change_token_hash; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.email_change_tokens
    ADD CONSTRAINT uq_email_change_token_hash UNIQUE (token_hash);

-- Name: email_verification_tokens uq_email_verification_token_hash; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.email_verification_tokens
    ADD CONSTRAINT uq_email_verification_token_hash UNIQUE (token_hash);

-- Name: endpoint_allowlist uq_endpoint_allowlist_host; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.endpoint_allowlist
    ADD CONSTRAINT uq_endpoint_allowlist_host UNIQUE (host);

-- Name: idempotency_records uq_idempotency_user_key; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.idempotency_records
    ADD CONSTRAINT uq_idempotency_user_key UNIQUE (user_id, idempotency_key);

-- Name: invoice_requests uq_invoice_requests_order; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.invoice_requests
    ADD CONSTRAINT uq_invoice_requests_order UNIQUE (order_no);

-- Name: mfa_challenges uq_mfa_challenge_token_hash; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.mfa_challenges
    ADD CONSTRAINT uq_mfa_challenge_token_hash UNIQUE (token_hash);

-- Name: model_catalog uq_model_catalog_provider_upstream; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_catalog
    ADD CONSTRAINT uq_model_catalog_provider_upstream UNIQUE (provider_id, upstream_name);

-- Name: model_prices uq_model_prices_version_meter_tier; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_prices
    ADD CONSTRAINT uq_model_prices_version_meter_tier UNIQUE (pricing_version_id, meter, tier_min_tokens);

-- Name: notifications uq_notifications_user_dedupe; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT uq_notifications_user_dedupe UNIQUE (user_id, dedupe_key);

-- Name: password_reset_tokens uq_password_reset_token_hash; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT uq_password_reset_token_hash UNIQUE (token_hash);

-- Name: payment_orders uq_payment_orders_order_no; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.payment_orders
    ADD CONSTRAINT uq_payment_orders_order_no UNIQUE (order_no);

-- Name: payment_orders uq_payment_orders_user_idempotency; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.payment_orders
    ADD CONSTRAINT uq_payment_orders_user_idempotency UNIQUE (user_id, idempotency_key);

-- Name: pricing_versions uq_pricing_versions_model_version; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.pricing_versions
    ADD CONSTRAINT uq_pricing_versions_model_version UNIQUE (model_id, version);

-- Name: refund_orders uq_refund_orders_order; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.refund_orders
    ADD CONSTRAINT uq_refund_orders_order UNIQUE (order_id);

-- Name: sanctioned_address_blocks uq_sanctioned_address_network; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.sanctioned_address_blocks
    ADD CONSTRAINT uq_sanctioned_address_network UNIQUE (address, network);

-- Name: sessions uq_sessions_token_hash; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT uq_sessions_token_hash UNIQUE (token_hash);

-- Name: totp_recovery_codes uq_totp_recovery_code_hash; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.totp_recovery_codes
    ADD CONSTRAINT uq_totp_recovery_code_hash UNIQUE (code_hash);

-- Name: usage_records uq_usage_records_request_id; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.usage_records
    ADD CONSTRAINT uq_usage_records_request_id UNIQUE (request_id);

-- Name: usage_records usage_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.usage_records
    ADD CONSTRAINT usage_records_pkey PRIMARY KEY (id);

-- Name: usage_settlements usage_settlements_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.usage_settlements
    ADD CONSTRAINT usage_settlements_pkey PRIMARY KEY (id);

-- Name: user_profiles user_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_pkey PRIMARY KEY (user_id);

-- Name: user_roles user_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (user_id, role_id);

-- Name: users users_email_normalized_key; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_normalized_key UNIQUE (email_normalized);

-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

-- ============================================================
-- 第二部分：索引（含高并发场景的部分索引）
-- ============================================================
-- Name: ix_account_ledger_user_created; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_account_ledger_user_created ON public.account_ledger USING btree (user_id, created_at);

-- Name: INDEX ix_account_ledger_user_created; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_account_ledger_user_created IS '高并发：用户按时间倒序翻页账单流水';

-- Name: ix_account_ledger_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_account_ledger_user_id ON public.account_ledger USING btree (user_id);

-- Name: INDEX ix_account_ledger_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_account_ledger_user_id IS '按用户查询账本流水';

-- Name: ix_api_keys_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_api_keys_user_id ON public.api_keys USING btree (user_id);

-- Name: INDEX ix_api_keys_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_api_keys_user_id IS '按用户查询密钥列表';

-- Name: ix_balance_holds_held_expiry; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_balance_holds_held_expiry ON public.balance_holds USING btree (expires_at) WHERE ((status)::text = 'held'::text);

-- Name: INDEX ix_balance_holds_held_expiry; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_balance_holds_held_expiry IS '高并发：过期预扣定时释放扫描（部分索引，只含 held）';

-- Name: ix_balance_holds_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_balance_holds_user_id ON public.balance_holds USING btree (user_id);

-- Name: INDEX ix_balance_holds_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_balance_holds_user_id IS '按用户查询预扣记录';

-- Name: ix_email_change_tokens_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_email_change_tokens_user_id ON public.email_change_tokens USING btree (user_id);

-- Name: INDEX ix_email_change_tokens_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_email_change_tokens_user_id IS '按用户查询换绑令牌';

-- Name: ix_email_verification_tokens_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_email_verification_tokens_user_id ON public.email_verification_tokens USING btree (user_id);

-- Name: INDEX ix_email_verification_tokens_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_email_verification_tokens_user_id IS '按用户查询验证令牌';

-- Name: ix_login_devices_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_login_devices_user_id ON public.login_devices USING btree (user_id);

-- Name: INDEX ix_login_devices_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_login_devices_user_id IS '按用户查询登录设备';

-- Name: ix_mfa_challenges_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_mfa_challenges_user_id ON public.mfa_challenges USING btree (user_id);

-- Name: INDEX ix_mfa_challenges_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_mfa_challenges_user_id IS '按用户查询 MFA 挑战';

-- Name: ix_model_catalog_provider_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_model_catalog_provider_id ON public.model_catalog USING btree (provider_id);

-- Name: INDEX ix_model_catalog_provider_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_model_catalog_provider_id IS '按供应商查询模型';

-- Name: ix_model_deployments_model_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_model_deployments_model_id ON public.model_deployments USING btree (model_id);

-- Name: INDEX ix_model_deployments_model_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_model_deployments_model_id IS '按模型查询部署';

-- Name: ix_model_prices_pricing_version_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_model_prices_pricing_version_id ON public.model_prices USING btree (pricing_version_id);

-- Name: INDEX ix_model_prices_pricing_version_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_model_prices_pricing_version_id IS '按定价版本查询价格明细';

-- Name: ix_model_sync_jobs_provider_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_model_sync_jobs_provider_id ON public.model_sync_jobs USING btree (provider_id);

-- Name: INDEX ix_model_sync_jobs_provider_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_model_sync_jobs_provider_id IS '按供应商查询同步任务';

-- Name: ix_model_test_runs_provider_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_model_test_runs_provider_id ON public.model_test_runs USING btree (provider_id);

-- Name: INDEX ix_model_test_runs_provider_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_model_test_runs_provider_id IS '按供应商查询测试记录';

-- Name: ix_notifications_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_notifications_user_id ON public.notifications USING btree (user_id);

-- Name: INDEX ix_notifications_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_notifications_user_id IS '按用户查询通知';

-- Name: ix_notifications_user_unread; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_notifications_user_unread ON public.notifications USING btree (user_id, created_at) WHERE (read_at IS NULL);

-- Name: INDEX ix_notifications_user_unread; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_notifications_user_unread IS '高并发：未读通知拉取（部分索引，只含未读）';

-- Name: ix_password_reset_tokens_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_password_reset_tokens_user_id ON public.password_reset_tokens USING btree (user_id);

-- Name: INDEX ix_password_reset_tokens_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_password_reset_tokens_user_id IS '按用户查询重置令牌';

-- Name: ix_payment_events_order_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_payment_events_order_id ON public.payment_events USING btree (order_id);

-- Name: INDEX ix_payment_events_order_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_payment_events_order_id IS '按订单查询回调事件';

-- Name: ix_payment_orders_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_payment_orders_user_id ON public.payment_orders USING btree (user_id);

-- Name: INDEX ix_payment_orders_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_payment_orders_user_id IS '按用户查询支付订单';

-- Name: ix_pricing_versions_model_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_pricing_versions_model_id ON public.pricing_versions USING btree (model_id);

-- Name: INDEX ix_pricing_versions_model_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_pricing_versions_model_id IS '按模型查询定价版本';

-- Name: ix_provider_credentials_provider_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_provider_credentials_provider_id ON public.provider_credentials USING btree (provider_id);

-- Name: INDEX ix_provider_credentials_provider_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_provider_credentials_provider_id IS '按供应商查询密钥';

-- Name: ix_sessions_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_sessions_user_id ON public.sessions USING btree (user_id);

-- Name: INDEX ix_sessions_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_sessions_user_id IS '按用户查询会话';

-- Name: ix_ticket_messages_ticket_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_ticket_messages_ticket_id ON public.ticket_messages USING btree (ticket_id);

-- Name: INDEX ix_ticket_messages_ticket_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_ticket_messages_ticket_id IS '按工单查询消息';

-- Name: ix_totp_recovery_codes_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_totp_recovery_codes_user_id ON public.totp_recovery_codes USING btree (user_id);

-- Name: INDEX ix_totp_recovery_codes_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_totp_recovery_codes_user_id IS '按用户查询恢复码';

-- Name: ix_usage_records_model_created; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_usage_records_model_created ON public.usage_records USING btree (model_id, created_at);

-- Name: INDEX ix_usage_records_model_created; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_usage_records_model_created IS '高并发：运营按模型维度统计用量';

-- Name: ix_usage_records_unsettled; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_usage_records_unsettled ON public.usage_records USING btree (created_at) WHERE ((settlement_status)::text = ANY (ARRAY[('pending'::character varying)::text, ('disputed'::character varying)::text]));

-- Name: INDEX ix_usage_records_unsettled; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_usage_records_unsettled IS '高并发：未完结结算定时扫描（部分索引，只含 pending/disputed）';

-- Name: ix_usage_records_user_created; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_usage_records_user_created ON public.usage_records USING btree (user_id, created_at);

-- Name: INDEX ix_usage_records_user_created; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_usage_records_user_created IS '高并发：用户按时间倒序翻页自己的用量历史';

-- Name: ix_usage_records_user_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_usage_records_user_id ON public.usage_records USING btree (user_id);

-- Name: INDEX ix_usage_records_user_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_usage_records_user_id IS '按用户查询用量记录';

-- Name: ix_usage_settlements_hold_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_usage_settlements_hold_id ON public.usage_settlements USING btree (hold_id);

-- Name: INDEX ix_usage_settlements_hold_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_usage_settlements_hold_id IS '高并发：结算记录按预扣反查';

-- Name: ix_usage_settlements_usage_record_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_usage_settlements_usage_record_id ON public.usage_settlements USING btree (usage_record_id);

-- Name: INDEX ix_usage_settlements_usage_record_id; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.ix_usage_settlements_usage_record_id IS '按用量记录查询结算';

-- Name: uq_crypto_tail_open; Type: INDEX; Schema: public; Owner: -

CREATE UNIQUE INDEX uq_crypto_tail_open ON public.crypto_deposit_intents USING btree (address, network, tail_amount) WHERE ((tail_status)::text = 'reserved'::text);

-- Name: INDEX uq_crypto_tail_open; Type: COMMENT; Schema: public; Owner: -

COMMENT ON INDEX public.uq_crypto_tail_open IS '同一地址+网络只允许一个未使用尾数（部分唯一索引）';

-- ============================================================
-- 第三部分：触发器（账本禁止 UPDATE / DELETE）
-- ============================================================
-- Name: account_ledger trg_reject_ledger_delete; Type: TRIGGER; Schema: public; Owner: -

CREATE TRIGGER trg_reject_ledger_delete BEFORE DELETE ON public.account_ledger FOR EACH ROW EXECUTE FUNCTION public._reject_ledger_write();

-- Name: account_ledger trg_reject_ledger_update; Type: TRIGGER; Schema: public; Owner: -

CREATE TRIGGER trg_reject_ledger_update BEFORE UPDATE ON public.account_ledger FOR EACH ROW EXECUTE FUNCTION public._reject_ledger_write();

-- ============================================================
-- 第四部分：外键约束
-- ============================================================
-- Name: account_balances account_balances_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.account_balances
    ADD CONSTRAINT account_balances_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;

-- Name: account_ledger account_ledger_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.account_ledger
    ADD CONSTRAINT account_ledger_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;

-- Name: account_ledger account_ledger_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.account_ledger
    ADD CONSTRAINT account_ledger_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;

-- Name: api_keys api_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: audit_events audit_events_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id) ON DELETE SET NULL;

-- Name: balance_holds balance_holds_api_key_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.balance_holds
    ADD CONSTRAINT balance_holds_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES public.api_keys(id) ON DELETE SET NULL;

-- Name: balance_holds balance_holds_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.balance_holds
    ADD CONSTRAINT balance_holds_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;

-- Name: content_audit_records content_audit_records_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.content_audit_records
    ADD CONSTRAINT content_audit_records_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;

-- Name: coupon_redemptions coupon_redemptions_coupon_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.coupon_redemptions
    ADD CONSTRAINT coupon_redemptions_coupon_id_fkey FOREIGN KEY (coupon_id) REFERENCES public.coupons(id) ON DELETE CASCADE;

-- Name: coupon_redemptions coupon_redemptions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.coupon_redemptions
    ADD CONSTRAINT coupon_redemptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: coupons coupons_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.coupons
    ADD CONSTRAINT coupons_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;

-- Name: crypto_deposit_intents crypto_deposit_intents_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.crypto_deposit_intents
    ADD CONSTRAINT crypto_deposit_intents_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.payment_orders(id) ON DELETE CASCADE;

-- Name: email_change_tokens email_change_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.email_change_tokens
    ADD CONSTRAINT email_change_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: email_verification_tokens email_verification_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.email_verification_tokens
    ADD CONSTRAINT email_verification_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: idempotency_records idempotency_records_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.idempotency_records
    ADD CONSTRAINT idempotency_records_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: invoice_requests invoice_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.invoice_requests
    ADD CONSTRAINT invoice_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: login_devices login_devices_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.login_devices
    ADD CONSTRAINT login_devices_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: mfa_challenges mfa_challenges_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.mfa_challenges
    ADD CONSTRAINT mfa_challenges_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: model_catalog model_catalog_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_catalog
    ADD CONSTRAINT model_catalog_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id) ON DELETE CASCADE;

-- Name: model_deployments model_deployments_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_deployments
    ADD CONSTRAINT model_deployments_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.model_catalog(id) ON DELETE CASCADE;

-- Name: model_deployments model_deployments_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_deployments
    ADD CONSTRAINT model_deployments_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id) ON DELETE CASCADE;

-- Name: model_prices model_prices_pricing_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_prices
    ADD CONSTRAINT model_prices_pricing_version_id_fkey FOREIGN KEY (pricing_version_id) REFERENCES public.pricing_versions(id) ON DELETE CASCADE;

-- Name: model_sync_jobs model_sync_jobs_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_sync_jobs
    ADD CONSTRAINT model_sync_jobs_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id) ON DELETE CASCADE;

-- Name: model_test_runs model_test_runs_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.model_test_runs
    ADD CONSTRAINT model_test_runs_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id) ON DELETE CASCADE;

-- Name: notification_preferences notification_preferences_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT notification_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: password_reset_tokens password_reset_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: payment_events payment_events_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.payment_events
    ADD CONSTRAINT payment_events_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.payment_orders(id) ON DELETE SET NULL;

-- Name: payment_orders payment_orders_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.payment_orders
    ADD CONSTRAINT payment_orders_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.recharge_products(id) ON DELETE SET NULL;

-- Name: payment_orders payment_orders_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.payment_orders
    ADD CONSTRAINT payment_orders_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;

-- Name: pricing_versions pricing_versions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.pricing_versions
    ADD CONSTRAINT pricing_versions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;

-- Name: pricing_versions pricing_versions_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.pricing_versions
    ADD CONSTRAINT pricing_versions_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.model_catalog(id) ON DELETE CASCADE;

-- Name: provider_credentials provider_credentials_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.provider_credentials
    ADD CONSTRAINT provider_credentials_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id) ON DELETE CASCADE;

-- Name: refund_orders refund_orders_executed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.refund_orders
    ADD CONSTRAINT refund_orders_executed_by_fkey FOREIGN KEY (executed_by) REFERENCES public.users(id);

-- Name: refund_orders refund_orders_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.refund_orders
    ADD CONSTRAINT refund_orders_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.payment_orders(id) ON DELETE RESTRICT;

-- Name: refund_orders refund_orders_requested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.refund_orders
    ADD CONSTRAINT refund_orders_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES public.users(id);

-- Name: refund_orders refund_orders_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.refund_orders
    ADD CONSTRAINT refund_orders_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);

-- Name: role_permissions role_permissions_permission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions(id) ON DELETE CASCADE;

-- Name: role_permissions role_permissions_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;

-- Name: sessions sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: ticket_messages ticket_messages_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.ticket_messages
    ADD CONSTRAINT ticket_messages_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: ticket_messages ticket_messages_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.ticket_messages
    ADD CONSTRAINT ticket_messages_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;

-- Name: tickets tickets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: totp_recovery_codes totp_recovery_codes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.totp_recovery_codes
    ADD CONSTRAINT totp_recovery_codes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: usage_records usage_records_api_key_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.usage_records
    ADD CONSTRAINT usage_records_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES public.api_keys(id) ON DELETE SET NULL;

-- Name: usage_records usage_records_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.usage_records
    ADD CONSTRAINT usage_records_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: usage_settlements usage_settlements_hold_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.usage_settlements
    ADD CONSTRAINT usage_settlements_hold_id_fkey FOREIGN KEY (hold_id) REFERENCES public.balance_holds(id) ON DELETE SET NULL;

-- Name: usage_settlements usage_settlements_ledger_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.usage_settlements
    ADD CONSTRAINT usage_settlements_ledger_entry_id_fkey FOREIGN KEY (ledger_entry_id) REFERENCES public.account_ledger(id) ON DELETE RESTRICT;

-- Name: usage_settlements usage_settlements_usage_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.usage_settlements
    ADD CONSTRAINT usage_settlements_usage_record_id_fkey FOREIGN KEY (usage_record_id) REFERENCES public.usage_records(id) ON DELETE CASCADE;

-- Name: user_profiles user_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Name: user_roles user_roles_granted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_granted_by_fkey FOREIGN KEY (granted_by) REFERENCES public.users(id) ON DELETE SET NULL;

-- Name: user_roles user_roles_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;

-- Name: user_roles user_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- ============================================================
-- 种子数据（严格按外键依赖顺序插入）
-- ============================================================

-- alembic_version（迁移版本对齐；新增迁移后请同步更新此值，否则 upgrade head 会重放历史迁移）
INSERT INTO public.alembic_version (version_num) VALUES ('20261102_0017_api_key_crypto') ON CONFLICT (version_num) DO NOTHING;

-- audit_chain_lock（独立表）
INSERT INTO public.audit_chain_lock (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- content_safety_settings（独立表，默认关闭）
INSERT INTO public.content_safety_settings (id, enabled) VALUES (1, false) ON CONFLICT (id) DO NOTHING;

-- roles（7 条独立）
INSERT INTO public.roles (id, code, name, description, is_system, created_at) VALUES ('00000000-0000-4000-8000-000000000001', 'user', 'User', '', true, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.roles (id, code, name, description, is_system, created_at) VALUES ('00000000-0000-4000-8000-000000000002', 'support', 'Support', '', true, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.roles (id, code, name, description, is_system, created_at) VALUES ('00000000-0000-4000-8000-000000000003', 'finance', 'Finance', '', true, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.roles (id, code, name, description, is_system, created_at) VALUES ('00000000-0000-4000-8000-000000000004', 'operator', 'Operator', '', true, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.roles (id, code, name, description, is_system, created_at) VALUES ('00000000-0000-4000-8000-000000000005', 'model_ops', 'Model ops', '', true, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.roles (id, code, name, description, is_system, created_at) VALUES ('00000000-0000-4000-8000-000000000006', 'admin', 'Admin', '', true, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.roles (id, code, name, description, is_system, created_at) VALUES ('00000000-0000-4000-8000-000000000007', 'superadmin', 'Superadmin', '', true, NOW()) ON CONFLICT (id) DO NOTHING;

-- permissions（9 条独立）
INSERT INTO public.permissions (id, code, description, created_at) VALUES ('00000000-0000-4000-8000-000000000101', 'admin:access', 'Access admin APIs', NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.permissions (id, code, description, created_at) VALUES ('00000000-0000-4000-8000-000000000102', 'user:ban', 'Freeze or unfreeze users', NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.permissions (id, code, description, created_at) VALUES ('00000000-0000-4000-8000-000000000103', 'ledger:adjust', 'Adjust ledger', NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.permissions (id, code, description, created_at) VALUES ('00000000-0000-4000-8000-000000000104', 'provider:credential:read', 'Read provider credentials', NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.permissions (id, code, description, created_at) VALUES ('00000000-0000-4000-8000-000000000105', 'rbac:assign', 'Assign roles', NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.permissions (id, code, description, created_at) VALUES ('00000000-0000-4000-8000-000000000106', 'refund:request', 'Request refunds', NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.permissions (id, code, description, created_at) VALUES ('00000000-0000-4000-8000-000000000107', 'refund:execute', 'Execute refunds', NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.permissions (id, code, description, created_at) VALUES ('00000000-0000-4000-8000-000000000108', 'provider:manage', 'Manage providers and endpoint allowlist', NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO public.permissions (id, code, description, created_at) VALUES ('00000000-0000-4000-8000-000000000109', 'model:publish', 'Confirm and publish models', NOW()) ON CONFLICT (id) DO NOTHING;

-- role_permissions（依赖 roles + permissions）
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000006', '00000000-0000-4000-8000-000000000101') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000006', '00000000-0000-4000-8000-000000000107') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000006', '00000000-0000-4000-8000-000000000102') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000006', '00000000-0000-4000-8000-000000000105') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000006', '00000000-0000-4000-8000-000000000108') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000006', '00000000-0000-4000-8000-000000000109') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000003', '00000000-0000-4000-8000-000000000106') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000005', '00000000-0000-4000-8000-000000000104') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000005', '00000000-0000-4000-8000-000000000108') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000005', '00000000-0000-4000-8000-000000000109') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000007', '00000000-0000-4000-8000-000000000101') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000007', '00000000-0000-4000-8000-000000000102') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000007', '00000000-0000-4000-8000-000000000105') ON CONFLICT DO NOTHING;
INSERT INTO public.role_permissions (role_id, permission_id) VALUES ('00000000-0000-4000-8000-000000000007', '00000000-0000-4000-8000-000000000103') ON CONFLICT DO NOTHING;

-- admin@forge.local / admin123，超级管理员
INSERT INTO public.users (
    id, email, email_normalized, password_hash, status,
    failed_login_count, totp_enabled, created_at, updated_at
) VALUES (
    '11111111-1111-4111-8000-111111111111',
    'admin@forge.local', 'admin@forge.local',
    '$argon2id$v=19$m=65536,t=3,p=4$GuHB5zKdZ2x/8RzkY+E/wg$lfEmAIbhnQgVu+N2HFDgcfoOxaneRMUuTQFzhhWRNHk',
    'active', 0, false,
    NOW(), NOW()
) ON CONFLICT (id) DO NOTHING;

-- user_roles（依赖 users + roles）
INSERT INTO public.user_roles (user_id, role_id, granted_by, granted_at) VALUES
    ('11111111-1111-4111-8000-111111111111', '00000000-0000-4000-8000-000000000007', NULL, NOW()),
    ('11111111-1111-4111-8000-111111111111', '00000000-0000-4000-8000-000000000006', NULL, NOW())
ON CONFLICT DO NOTHING;

-- ============================================================
-- 正式环境 SQL 执行完毕
-- 默认超级管理员: admin@forge.local / admin123
-- 立即登录并修改密码！
-- ============================================================
