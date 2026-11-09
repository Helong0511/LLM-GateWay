-- 账本不变量。只读。金额比较使用 numeric，不要改成 float。
-- 1. 余额 = 贷方合计 - 借方合计。方向 N 不进入余额。
-- 2. 生效中预扣 = status 为 held 的预扣金额合计。
-- 3. 冻结 = freeze 合计 - unfreeze 合计。
-- 4. 可用余额 = 余额 - 预扣 - 冻结，并且不能为负。

SELECT
    b.user_id,
    b.currency,
    b.balance,
    b.held,
    b.frozen,
    b.balance - b.held - b.frozen AS available,
    COALESCE(l.net, 0) AS ledger_net,
    COALESCE(h.held, 0) AS open_holds,
    COALESCE(f.frozen, 0) AS frozen_net
FROM account_balances AS b
LEFT JOIN (
    SELECT
        user_id,
        currency,
        SUM(CASE direction WHEN 'C' THEN amount WHEN 'D' THEN -amount ELSE 0 END) AS net
    FROM account_ledger
    GROUP BY user_id, currency
) AS l ON l.user_id = b.user_id AND l.currency = b.currency
LEFT JOIN (
    SELECT user_id, currency, SUM(amount) AS held
    FROM balance_holds
    WHERE status = 'held'
    GROUP BY user_id, currency
) AS h ON h.user_id = b.user_id AND h.currency = b.currency
LEFT JOIN (
    SELECT
        user_id,
        currency,
        SUM(CASE entry_type WHEN 'freeze' THEN amount WHEN 'unfreeze' THEN -amount ELSE 0 END) AS frozen
    FROM account_ledger
    GROUP BY user_id, currency
) AS f ON f.user_id = b.user_id AND f.currency = b.currency
WHERE b.balance IS DISTINCT FROM COALESCE(l.net, 0)
   OR b.held IS DISTINCT FROM COALESCE(h.held, 0)
   OR b.frozen IS DISTINCT FROM COALESCE(f.frozen, 0)
   OR b.balance < b.held + b.frozen;

-- 仍未关闭的预扣。每一笔最终只能是 committed 或 released。
SELECT id, user_id, request_id, amount, status, expires_at
FROM balance_holds
WHERE status = 'held'
ORDER BY expires_at;
