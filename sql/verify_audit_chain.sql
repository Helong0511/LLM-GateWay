-- 审计链衔接检查。只读。
-- 内容哈希要由服务重新计算，对应 GET /api/admin/audit/verify。
-- 这里只检查序号连续，以及后一条的 prev_hash 等于前一条的 content_hash。


-- 登录页是同一个：http://127.0.0.1:3000/login。进去之后再打开对应地址。

-- 客户端

-- 地址：http://127.0.0.1:3000/console
-- 邮箱：billing-check@example.com
-- 密码：Correct-horse-1
-- 这个账号是普通用户，打开管理后台会被拒绝。

-- 管理员端

-- 下面是 cloudflare 的 验证密码
-- 765869276
-- 566936963
-- 539551895
-- 611437015
-- 095100467
-- 928659920
-- 108030536
-- 164095746
-- 地址：http://127.0.0.1:3000/admin
-- 用户列表：http://127.0.0.1:3000/admin/users
-- 邮箱：admin@example.com
-- 密码：Forge-admin-1

SELECT a.seq AS broken_seq
FROM audit_events AS a
LEFT JOIN audit_events AS b ON b.seq = a.seq - 1
WHERE a.seq > 1
  AND (b.seq IS NULL OR a.prev_hash IS DISTINCT FROM b.content_hash)
ORDER BY a.seq;
