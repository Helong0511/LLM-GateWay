-- 工单、发票、公告、优惠券、内容审计和任务记录。与迁移 20261029_0008 一致。

CREATE TABLE IF NOT EXISTS tickets (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    category varchar(16) NOT NULL,
    subject varchar(160) NOT NULL,
    status varchar(16) NOT NULL,
    priority varchar(16) NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT ck_tickets_category CHECK (category IN ('billing', 'technical', 'refund', 'chain', 'other')),
    CONSTRAINT ck_tickets_status CHECK (status IN ('open', 'pending', 'resolved', 'closed')),
    CONSTRAINT ck_tickets_priority CHECK (priority IN ('low', 'normal', 'high'))
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id uuid PRIMARY KEY,
    ticket_id uuid NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    author_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    body text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS invoice_requests (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    order_no varchar(40) NOT NULL,
    title varchar(160) NOT NULL,
    tax_no varchar(64) NOT NULL,
    amount numeric(24, 8) NOT NULL,
    currency varchar(8) NOT NULL,
    status varchar(16) NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT uq_invoice_requests_order UNIQUE (order_no),
    CONSTRAINT ck_invoice_requests_status CHECK (status IN ('requested', 'issued', 'rejected')),
    CONSTRAINT ck_invoice_requests_amount CHECK (amount > 0)
);

CREATE TABLE IF NOT EXISTS announcements (
    id uuid PRIMARY KEY,
    slug varchar(80) NOT NULL,
    title varchar(160) NOT NULL,
    body text NOT NULL,
    published boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_announcements_slug UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS coupons (
    id uuid PRIMARY KEY,
    code varchar(32) NOT NULL,
    bonus_amount numeric(24, 8) NOT NULL,
    currency varchar(8) NOT NULL,
    max_uses integer NOT NULL,
    used_count integer NOT NULL,
    enabled boolean NOT NULL,
    expires_at timestamptz,
    created_at timestamptz NOT NULL,
    CONSTRAINT uq_coupons_code UNIQUE (code),
    CONSTRAINT ck_coupons_bonus CHECK (bonus_amount > 0),
    CONSTRAINT ck_coupons_uses CHECK (max_uses >= 1 AND used_count >= 0 AND used_count <= max_uses)
);

CREATE TABLE IF NOT EXISTS coupon_redemptions (
    id uuid PRIMARY KEY,
    coupon_id uuid NOT NULL REFERENCES coupons (id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL,
    CONSTRAINT uq_coupon_redemptions_user UNIQUE (coupon_id, user_id)
);

CREATE TABLE IF NOT EXISTS content_safety_settings (
    id integer PRIMARY KEY,
    enabled boolean NOT NULL
);

INSERT INTO content_safety_settings (id, enabled)
VALUES (1, false)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS content_audit_records (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES users (id) ON DELETE SET NULL,
    model_name varchar(128) NOT NULL,
    category varchar(32) NOT NULL,
    summary_hash varchar(64) NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS job_runs (
    id uuid PRIMARY KEY,
    name varchar(64) NOT NULL,
    status varchar(16) NOT NULL,
    detail varchar(256) NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_job_runs_status CHECK (status IN ('succeeded', 'failed'))
);
