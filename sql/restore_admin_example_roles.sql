-- 恢复开发账号 admin@example.com 的管理角色（幂等，可反复执行）
-- 用法（本机）：
--   psql "postgresql://forge:forge-dev-only@127.0.0.1:5432/forge" -f sql/restore_admin_example_roles.sql
-- 或在任意 SQL 客户端连到 forge 库后整文件执行。
--
-- 角色 UUID 与 apps/api/app/auth/rbac.py 中 ROLE_IDS 保持一致：
--   user        00000000-0000-4000-8000-000000000001
--   admin       00000000-0000-4000-8000-000000000006
--   superadmin  00000000-0000-4000-8000-000000000007

BEGIN;

-- 确认账号存在
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM users
    WHERE email_normalized = 'admin@example.com'
       OR lower(email) = 'admin@example.com'
  ) THEN
    RAISE EXCEPTION '用户 admin@example.com 不存在，请先完成注册/初始化';
  END IF;
END $$;

-- 确保账号为正常状态（可选：若被误冻结则解开）
UPDATE users
SET status = 'active',
    updated_at = NOW()
WHERE (email_normalized = 'admin@example.com' OR lower(email) = 'admin@example.com')
  AND status <> 'deleted';

-- 补回普通用户 / 系统管理员 / 超级管理员（已有则跳过）
INSERT INTO user_roles (user_id, role_id, granted_at)
SELECT u.id, r.id, NOW()
FROM users u
CROSS JOIN (
  VALUES
    ('00000000-0000-4000-8000-000000000001'::uuid),  -- user
    ('00000000-0000-4000-8000-000000000006'::uuid),  -- admin
    ('00000000-0000-4000-8000-000000000007'::uuid)   -- superadmin
) AS roles(id)
JOIN roles r ON r.id = roles.id
WHERE (u.email_normalized = 'admin@example.com' OR lower(u.email) = 'admin@example.com')
  AND NOT EXISTS (
    SELECT 1
    FROM user_roles ur
    WHERE ur.user_id = u.id
      AND ur.role_id = r.id
  );

COMMIT;

-- 核对结果
SELECT u.email, u.status, r.code AS role_code, r.name AS role_name
FROM users u
JOIN user_roles ur ON ur.user_id = u.id
JOIN roles r ON r.id = ur.role_id
WHERE u.email_normalized = 'admin@example.com'
   OR lower(u.email) = 'admin@example.com'
ORDER BY r.code;
