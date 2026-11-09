-- 区分启用 / 停用 / 删除（与 alembic 20261030_0010 一致）

ALTER TABLE recharge_products
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;

ALTER TABLE coupons
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;

ALTER TABLE providers DROP CONSTRAINT IF EXISTS ck_providers_status;
ALTER TABLE providers
  ADD CONSTRAINT ck_providers_status
  CHECK (status IN ('active', 'disabled', 'deleted'));

ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS ck_api_keys_status;
ALTER TABLE api_keys
  ADD CONSTRAINT ck_api_keys_status
  CHECK (status IN ('active', 'disabled', 'revoked', 'expired'));
