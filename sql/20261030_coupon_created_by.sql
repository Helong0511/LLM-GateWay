-- 优惠券增加创建人（与 alembic 20261030_0009 一致）
ALTER TABLE coupons
  ADD COLUMN IF NOT EXISTS created_by UUID NULL REFERENCES users(id) ON DELETE SET NULL;

UPDATE coupons AS c
SET created_by = a.actor_id
FROM (
  SELECT DISTINCT ON (target_id) target_id, actor_id
  FROM audit_events
  WHERE action = 'coupon.create' AND target_type = 'coupon' AND actor_id IS NOT NULL
  ORDER BY target_id, seq ASC
) AS a
WHERE c.id::text = a.target_id AND c.created_by IS NULL;
