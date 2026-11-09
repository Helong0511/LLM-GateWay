-- 与 alembic 20261102_0011 一致：同步上游时保存建议单价（每 token）

ALTER TABLE model_catalog
  ADD COLUMN IF NOT EXISTS upstream_input_price NUMERIC(24, 8) NULL;

ALTER TABLE model_catalog
  ADD COLUMN IF NOT EXISTS upstream_output_price NUMERIC(24, 8) NULL;
