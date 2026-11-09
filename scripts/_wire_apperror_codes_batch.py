# -*- coding: utf-8 -*-
"""Replace Chinese AppError messages with stable codes in auth/payments/keys."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"e:/ZZZ")

# (old_snippet, new_snippet) exact replacements
AUTH_SERVICE = [
    ('raise AppError(400, "VALIDATION_ERROR", "需要同意服务条款和隐私政策")',
     'raise AppError(400, "AUTH_TERMS_REQUIRED")'),
    ('raise AppError(429, "RATE_LIMITED", "当前网络注册过于频繁，请稍后再试")',
     'raise AppError(429, "AUTH_REGISTER_RATE_LIMITED")'),
    ('raise AppError(401, "UNAUTHENTICATED", "邮箱或密码不正确")',
     'raise AppError(401, "AUTH_BAD_CREDENTIALS")'),
    ('raise AppError(403, "FORBIDDEN", "账号已冻结")',
     'raise AppError(403, "ACCOUNT_FROZEN")'),
    ('raise AppError(400, "TOKEN_INVALID", "二次验证已失效，请重新登录")',
     'raise AppError(400, "AUTH_TOTP_CHALLENGE_EXPIRED")'),
    ('raise AppError(400, "TOKEN_INVALID", "验证码不正确")',
     'raise AppError(400, "AUTH_TOTP_BAD_CODE")'),
    ('raise AppError(404, "NOT_FOUND", "资料不存在")',
     'raise AppError(404, "PROFILE_NOT_FOUND")'),
    ('raise AppError(400, "VALIDATION_ERROR", "语言只能是 zh-CN、zh-TW 或 en")',
     'raise AppError(400, "LOCALE_INVALID")'),
    ('raise AppError(400, "VALIDATION_ERROR", "时区名称无法识别，请使用如 Asia/Shanghai 的标准时区") from exc',
     'raise AppError(400, "TIMEZONE_INVALID") from exc'),
    ('raise AppError(404, "NOT_FOUND", "会话不存在")',
     'raise AppError(404, "SESSION_NOT_FOUND")'),
    ('raise AppError(401, "UNAUTHENTICATED", "当前密码不正确")',
     'raise AppError(401, "AUTH_BAD_CURRENT_PASSWORD")'),
    ('raise AppError(400, "VALIDATION_ERROR", "新邮箱与当前邮箱相同")',
     'raise AppError(400, "EMAIL_SAME_AS_CURRENT")'),
    ('raise AppError(409, "VALIDATION_ERROR", "二次验证已开启")',
     'raise AppError(409, "TOTP_ALREADY_ENABLED")'),
    ('raise AppError(400, "VALIDATION_ERROR", "请先生成二次验证种子")',
     'raise AppError(400, "TOTP_SEED_REQUIRED")'),
    ('raise AppError(403, "FORBIDDEN", "初始化口令已被使用，超级管理员应已创建")',
     'raise AppError(403, "BOOTSTRAP_TOKEN_USED")'),
    ('raise AppError(403, "FORBIDDEN", "初始化口令文件不存在，请先按文档生成")',
     'raise AppError(403, "BOOTSTRAP_TOKEN_MISSING")'),
    ('raise AppError(403, "FORBIDDEN", "初始化口令不正确")',
     'raise AppError(403, "BOOTSTRAP_TOKEN_INVALID")'),
    ('raise AppError(409, "VALIDATION_ERROR", "超级管理员已存在，无需再次初始化")',
     'raise AppError(409, "BOOTSTRAP_ALREADY_DONE")'),
    ('raise AppError(403, "FORBIDDEN", "不能通过该接口分配超级管理员")',
     'raise AppError(403, "ROLE_SUPERADMIN_FORBIDDEN")'),
    ('raise AppError(400, "VALIDATION_ERROR", "角色不存在")',
     'raise AppError(400, "ROLE_NOT_FOUND")'),
    ('raise AppError(404, "NOT_FOUND", "用户不存在")',
     'raise AppError(404, "USER_NOT_FOUND")'),
    ('raise AppError(429, "RATE_LIMITED", "发送过于频繁，请稍后再试")',
     'raise AppError(429, "MAIL_SEND_RATE_LIMITED")'),
    ('raise AppError(429, "RATE_LIMITED", "今日发送次数已达上限")',
     'raise AppError(429, "MAIL_DAILY_LIMIT")'),
    ('raise AppError(400, "TOKEN_INVALID", "验证链接或令牌无效，请重新获取")',
     'raise AppError(400, "TOKEN_INVALID")'),
    ('raise AppError(400, "TOKEN_INVALID", "尝试验证次数过多，请重新获取新的链接或令牌")',
     'raise AppError(400, "TOKEN_TOO_MANY_ATTEMPTS")'),
    ('raise AppError(400, "TOKEN_INVALID", "验证链接或令牌已过期，请重新获取")',
     'raise AppError(400, "TOKEN_EXPIRED")'),
    ('raise AppError(400, "TOKEN_INVALID", "验证码或令牌不正确")',
     'raise AppError(400, "TOKEN_MISMATCH")'),
]

AUTH_PASSWORDS = [
    ('raise AppError(400, "VALIDATION_ERROR", "邮箱格式不正确")',
     'raise AppError(400, "EMAIL_INVALID")'),
    ('raise AppError(400, "VALIDATION_ERROR", "密码长度需要在 10 到 128 之间")',
     'raise AppError(400, "PASSWORD_LENGTH")'),
    ('raise AppError(400, "VALIDATION_ERROR", "密码需要同时包含字母和数字")',
     'raise AppError(400, "PASSWORD_COMPLEXITY")'),
    ('raise AppError(400, "VALIDATION_ERROR", "密码过于常见")',
     'raise AppError(400, "PASSWORD_COMMON")'),
]

AUTH_DEPS = [
    ('raise AppError(403, "FORBIDDEN", "当前来源地址不被允许访问此接口")',
     'raise AppError(403, "ORIGIN_FORBIDDEN")'),
]

AUTH_EMAILER = [
    ('raise AppError(503, "MAIL_NOT_CONFIGURED", "邮件服务未配置，邮件没有发出")',
     'raise AppError(503, "MAIL_NOT_CONFIGURED")'),
]

PAYMENTS = [
    ('raise AppError(400, "VALIDATION_ERROR", "请在请求头提供 Idempotency-Key，避免重复下单")',
     'raise AppError(400, "IDEMPOTENCY_KEY_REQUIRED")'),
    ('raise AppError(404, "NOT_FOUND", "充值套餐不存在")',
     'raise AppError(404, "PRODUCT_NOT_FOUND")'),
    ('raise AppError(404, "NOT_FOUND", "充值套餐已删除，不能购买")',
     'raise AppError(404, "PRODUCT_DELETED")'),
    ('raise AppError(404, "NOT_FOUND", "充值套餐已停用，暂时不能购买")',
     'raise AppError(404, "PRODUCT_DISABLED")'),
    ('raise AppError(400, "VALIDATION_ERROR", "该套餐币种与当前结算币不一致，不能购买")',
     'raise AppError(400, "PRODUCT_CURRENCY_MISMATCH")'),
    ('raise AppError(409, "IDEMPOTENCY_CONFLICT", "重复提交：该幂等键已被使用，请更换后重试") from exc',
     'raise AppError(409, "IDEMPOTENCY_KEY_REUSED") from exc'),
    ('raise AppError(400, "VALIDATION_ERROR", "对账状态只能是 unchecked / matched / disputed")',
     'raise AppError(400, "RECONCILE_STATUS_INVALID")'),
    ('raise AppError(404, "NOT_FOUND", "订单不存在")',
     'raise AppError(404, "ORDER_NOT_FOUND")'),
    ('raise AppError(400, "VALIDATION_ERROR", "只有已入账订单（已完成/多付）才能标记对账结果")',
     'raise AppError(400, "RECONCILE_ORDER_NOT_CREDITED")'),
    ('raise AppError(403, "FORBIDDEN", "当前环境未开启模拟支付")',
     'raise AppError(403, "MOCK_PAYMENTS_DISABLED")'),
    ('raise AppError(400, "VALIDATION_ERROR", "该订单不是模拟支付渠道，不能用模拟确认")',
     'raise AppError(400, "MOCK_CHANNEL_REQUIRED")'),
    ('raise AppError(400, "VALIDATION_ERROR", "订单已过期，请重新下单")',
     'raise AppError(400, "ORDER_EXPIRED")'),
    ('raise AppError(400, "VALIDATION_ERROR", "USDT 退款只能退回原付款地址")',
     'raise AppError(400, "REFUND_USDT_DESTINATION")'),
    ('raise AppError(409, "IDEMPOTENCY_CONFLICT", "该订单已有退款单，不能重复发起")',
     'raise AppError(409, "REFUND_ALREADY_EXISTS")'),
    ('raise AppError(403, "FORBIDDEN", "退款发起人不能复核自己的单，请换另一名财务")',
     'raise AppError(403, "REFUND_SELF_REVIEW_FORBIDDEN")'),
    ('raise AppError(403, "FORBIDDEN", "退款发起人不能拒绝自己的单，请换另一名财务")',
     'raise AppError(403, "REFUND_SELF_REJECT_FORBIDDEN")'),
    ('raise AppError(403, "FORBIDDEN", "退款执行人必须是发起人、复核人之外的第三人")',
     'raise AppError(403, "REFUND_EXECUTOR_MUST_BE_THIRD")'),
    ('raise AppError(400, "VALIDATION_ERROR", "当前汇率偏离过大，已拒绝下单，请稍后再试")',
     'raise AppError(400, "FX_DEVIATION_TOO_HIGH")'),
    ('raise AppError(503, "DEPENDENCY_UNAVAILABLE", "USDT 固定收款地址尚未配置，暂时无法下单")',
     'raise AppError(503, "USDT_ADDRESS_UNCONFIGURED")'),
    ('raise AppError(503, "DEPENDENCY_UNAVAILABLE", "USDT 尾数池已满，请稍后再试或换其他渠道")',
     'raise AppError(503, "USDT_TAIL_POOL_FULL")'),
    ('raise AppError(400, "VALIDATION_ERROR", "请提供合法的 Idempotency-Key（1～80 个字符）")',
     'raise AppError(400, "IDEMPOTENCY_KEY_INVALID")'),
    ('raise AppError(400, "VALIDATION_ERROR", "海外模式不能使用微信/支付宝，请改用 Stripe 或 USDT")',
     'raise AppError(400, "CHANNEL_NOT_ALLOWED_OVERSEAS")'),
    ('raise AppError(400, "VALIDATION_ERROR", "大陆模式不能使用 Stripe/USDT，请改用微信或支付宝")',
     'raise AppError(400, "CHANNEL_NOT_ALLOWED_CN")'),
    ('raise AppError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键对应的请求内容不一致，请更换键后重试")',
     'raise AppError(409, "IDEMPOTENCY_PAYLOAD_MISMATCH")'),
    ('raise AppError(404, "NOT_FOUND", "退款单不存在")',
     'raise AppError(404, "REFUND_NOT_FOUND")'),
]

# f-string / multi-arg cases handled separately in file edits
KEYS = [
    ('raise AppError(400, "VALIDATION_ERROR", "密钥名称需要在 1 到 128 个字符之间")',
     'raise AppError(400, "KEY_NAME_INVALID")'),
    ('raise AppError(400, "VALIDATION_ERROR", "密钥状态不支持，请使用列表中的状态")',
     'raise AppError(400, "KEY_STATUS_INVALID")'),
    ('raise AppError(404, "NOT_FOUND", "密钥不存在")',
     'raise AppError(404, "KEY_NOT_FOUND")'),
    ('raise AppError(401, "INVALID_API_KEY", "API Key 格式不正确（应以 sk- 开头）")',
     'raise AppError(401, "API_KEY_BAD_FORMAT")'),
    ('raise AppError(401, "INVALID_API_KEY", "API Key 已失效（可能已吊销或已过期）")',
     'raise AppError(401, "API_KEY_INVALID")'),
    ('raise AppError(401, "INVALID_API_KEY", "API Key 不存在")',
     'raise AppError(401, "API_KEY_MISSING")'),
    ('raise AppError(401, "INVALID_API_KEY", "API Key 已删除（吊销），不能再使用")',
     'raise AppError(401, "API_KEY_REVOKED")'),
    ('raise AppError(401, "INVALID_API_KEY", "API Key 已过期")',
     'raise AppError(401, "API_KEY_EXPIRED")'),
    ('raise AppError(403, "FORBIDDEN", "API Key 已停用，暂时不能调用；可在控制台重新启用")',
     'raise AppError(403, "API_KEY_DISABLED")'),
    ('raise AppError(403, "FORBIDDEN", "来源 IP 不在该密钥的白名单中")',
     'raise AppError(403, "API_KEY_IP_DENIED")'),
    ('raise AppError(402, "INSUFFICIENT_BALANCE", "该密钥的预算已用完，请提高预算或更换密钥")',
     'raise AppError(402, "API_KEY_BUDGET_EXCEEDED")'),
    ('raise AppError(403, "FORBIDDEN", "该密钥无权调用此模型，请在密钥权限中勾选该模型")',
     'raise AppError(403, "API_KEY_MODEL_DENIED")'),
    ('raise AppError(404, "NOT_FOUND", "调用记录不存在")',
     'raise AppError(404, "USAGE_NOT_FOUND")'),
    ('raise AppError(400, "VALIDATION_ERROR", "到期时间格式不正确，请使用带时区的 ISO 时间") from exc',
     'raise AppError(400, "KEY_EXPIRES_BAD_FORMAT") from exc'),
    ('raise AppError(400, "VALIDATION_ERROR", "到期时间必须带时区（例如以 Z 或 +08:00 结尾）")',
     'raise AppError(400, "KEY_EXPIRES_TZ_REQUIRED")'),
    ('raise AppError(400, "VALIDATION_ERROR", "预算必须是有效的十进制数字") from exc',
     'raise AppError(400, "KEY_BUDGET_BAD_FORMAT") from exc'),
    ('raise AppError(400, "VALIDATION_ERROR", "预算必须大于 0")',
     'raise AppError(400, "KEY_BUDGET_POSITIVE")'),
    ('raise AppError(400, "VALIDATION_ERROR", "排序字段不支持，请使用列表中的字段名")',
     'raise AppError(400, "SORT_FIELD_INVALID")'),
    ('raise AppError(400, "VALIDATION_ERROR", "结算状态不支持，请使用列表中的状态")',
     'raise AppError(400, "SETTLEMENT_STATUS_INVALID")'),
]

FILES = {
    "apps/api/app/auth/service.py": AUTH_SERVICE,
    "apps/api/app/auth/passwords.py": AUTH_PASSWORDS,
    "apps/api/app/auth/deps.py": AUTH_DEPS,
    "apps/api/app/auth/emailer.py": AUTH_EMAILER,
    "apps/api/app/payments/service.py": PAYMENTS,
    "apps/api/app/payments/router.py": PAYMENTS[:1],  # idempotency header
    "apps/api/app/keys/service.py": KEYS,
    "apps/api/app/keys/router.py": [
        p for p in KEYS if "KEY_EXPIRES" in p[1] or "KEY_BUDGET" in p[1] or "SORT_" in p[1] or "SETTLEMENT_" in p[1]
    ],
}


def apply_pairs(path: Path, pairs: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    orig = text
    for old, new in pairs:
        if old not in text:
            print(f"WARN missing in {path.name}: {old[:70]!r}")
            continue
        text = text.replace(old, new)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print(f"updated {path}")
    else:
        print(f"no change {path}")


def main() -> None:
    for rel, pairs in FILES.items():
        apply_pairs(ROOT / rel, pairs)

    # payments f-string / remaining specials
    pay = ROOT / "apps/api/app/payments/service.py"
    text = pay.read_text(encoding="utf-8")
    specials = [
        (
            'raise AppError(400, "VALIDATION_ERROR", f"订单状态「{status}」不支持筛选")',
            'raise AppError(400, "ORDER_STATUS_FILTER_INVALID", details={"status": status})',
        ),
        (
            'raise AppError(400, "VALIDATION_ERROR", f"订单当前状态为「{order.status}」，不能再确认")',
            'raise AppError(400, "ORDER_CONFIRM_STATUS_INVALID", details={"status": order.status})',
        ),
        (
            'raise AppError(400, "VALIDATION_ERROR", f"不支持的对账渠道「{channel}」")',
            'raise AppError(400, "RECONCILE_CHANNEL_INVALID", details={"channel": channel})',
        ),
        (
            'raise AppError(400, "VALIDATION_ERROR", f"订单状态为「{order.status}」，尚未入账，不能退款")',
            'raise AppError(400, "REFUND_ORDER_NOT_CREDITED", details={"status": order.status})',
        ),
        (
            'raise AppError(400, "VALIDATION_ERROR", f"退款单当前状态为「{refund.status}」，不是待复核，不能复核")',
            'raise AppError(400, "REFUND_NOT_PENDING_REVIEW", details={"status": refund.status})',
        ),
        (
            'raise AppError(400, "VALIDATION_ERROR", f"退款单当前状态为「{refund.status}」，须先完成复核再执行")',
            'raise AppError(400, "REFUND_NOT_REVIEWED", details={"status": refund.status})',
        ),
        (
            'raise AppError(400, "VALIDATION_ERROR", f"不支持的支付渠道「{channel}」")',
            'raise AppError(400, "CHANNEL_UNSUPPORTED", details={"channel": channel})',
        ),
    ]
    for old, new in specials:
        if old not in text:
            print(f"WARN pay special missing: {old[:60]!r}")
        else:
            text = text.replace(old, new)
            print("pay special ok")
    pay.write_text(text, encoding="utf-8")

    keys = ROOT / "apps/api/app/keys/service.py"
    kt = keys.read_text(encoding="utf-8")
    old = 'raise AppError(401, "INVALID_API_KEY", f"API Key 当前状态为「{row.status}」，不能使用")'
    new = 'raise AppError(401, "API_KEY_STATUS_INVALID", details={"status": row.status})'
    if old in kt:
        keys.write_text(kt.replace(old, new), encoding="utf-8")
        print("keys status special ok")
    else:
        print("WARN keys status special missing")


if __name__ == "__main__":
    main()
