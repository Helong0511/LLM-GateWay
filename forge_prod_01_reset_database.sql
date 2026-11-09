-- ============================================================
-- Forge API · 初始化第 1 步：删除并重建数据库
-- 版本: 2026-11-03
-- 适用: Navicat Premium 17 / pgAdmin / DBeaver / DataGrip
-- 数据库: PostgreSQL 15+
-- 字符集: UTF-8（本文件必须以 UTF-8 无 BOM 保存与导入）
--
-- 执行位置: 连接 postgres 库（不要连在 forge 库上）
-- 执行用户: postgres 超级用户（DROP / CREATE DATABASE 需要超级用户）
-- 执行结果: forge 库被彻底删除，并按 UTF-8 重建为空库（owner=forge，已授权）
-- 下一步: 切换到 forge 库，执行 forge_prod_02_init_schema.sql
-- 注意: DROP DATABASE 不能在事务块内执行；Navicat 默认自动提交即可
-- ============================================================

SET client_encoding = 'UTF8';

-- 1) 断开 forge 库上的所有会话，避免 DROP DATABASE 失败
SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
 WHERE datname = 'forge'
   AND pid <> pg_backend_pid();

-- 2) 删除旧库（存在才删，FORCE 可兜底强制断开残留连接）
DROP DATABASE IF EXISTS forge WITH (FORCE);

-- 3) 重新创建空库（排序规则与历史 forge 库保持一致）
CREATE DATABASE forge
  WITH ENCODING = 'UTF8'
       LC_COLLATE = 'en_US.UTF-8'
       LC_CTYPE   = 'en_US.UTF-8'
       TEMPLATE   = template0
       OWNER      = forge;

-- 4) 授权
GRANT CONNECT ON DATABASE forge TO forge;
GRANT ALL PRIVILEGES ON DATABASE forge TO forge;
