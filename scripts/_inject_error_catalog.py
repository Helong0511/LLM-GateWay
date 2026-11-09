# -*- coding: utf-8 -*-
"""Inject new AppError codes into MESSAGE_BY_CODE and frontend t.errors."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"e:/ZZZ")

# code -> (zh-CN default for API, en, zh-TW)
CATALOG: dict[str, tuple[str, str, str]] = {
    # auth
    "AUTH_TERMS_REQUIRED": (
        "需要同意服务条款和隐私政策",
        "You must accept the terms and privacy policy.",
        "需要同意服務條款與隱私政策",
    ),
    "AUTH_REGISTER_RATE_LIMITED": (
        "当前网络注册过于频繁，请稍后再试",
        "Too many registrations from this network. Try again later.",
        "目前網路註冊過於頻繁，請稍後再試",
    ),
    "AUTH_BAD_CREDENTIALS": (
        "邮箱或密码不正确",
        "Incorrect email or password.",
        "電子郵件或密碼不正確",
    ),
    "ACCOUNT_FROZEN": (
        "账号已冻结",
        "This account is frozen.",
        "帳號已凍結",
    ),
    "AUTH_TOTP_CHALLENGE_EXPIRED": (
        "二次验证已失效，请重新登录",
        "Two-factor challenge expired. Sign in again.",
        "二次驗證已失效，請重新登入",
    ),
    "AUTH_TOTP_BAD_CODE": (
        "验证码不正确",
        "Incorrect verification code.",
        "驗證碼不正確",
    ),
    "PROFILE_NOT_FOUND": (
        "资料不存在",
        "Profile not found.",
        "資料不存在",
    ),
    "LOCALE_INVALID": (
        "语言只能是 zh-CN、zh-TW 或 en",
        "Locale must be zh-CN, zh-TW, or en.",
        "語言只能是 zh-CN、zh-TW 或 en",
    ),
    "TIMEZONE_INVALID": (
        "时区名称无法识别，请使用如 Asia/Shanghai 的标准时区",
        "Unrecognized timezone. Use a standard name such as Asia/Shanghai.",
        "時區名稱無法識別，請使用如 Asia/Shanghai 的標準時區",
    ),
    "SESSION_NOT_FOUND": (
        "会话不存在",
        "Session not found.",
        "工作階段不存在",
    ),
    "AUTH_BAD_CURRENT_PASSWORD": (
        "当前密码不正确",
        "Current password is incorrect.",
        "目前密碼不正確",
    ),
    "EMAIL_SAME_AS_CURRENT": (
        "新邮箱与当前邮箱相同",
        "New email is the same as the current email.",
        "新電子郵件與目前電子郵件相同",
    ),
    "EMAIL_INVALID": (
        "邮箱格式不正确",
        "Invalid email format.",
        "電子郵件格式不正確",
    ),
    "PASSWORD_LENGTH": (
        "密码长度需要在 10 到 128 之间",
        "Password length must be between 10 and 128.",
        "密碼長度需在 10 到 128 之間",
    ),
    "PASSWORD_COMPLEXITY": (
        "密码需要同时包含字母和数字",
        "Password must include both letters and digits.",
        "密碼需要同時包含字母與數字",
    ),
    "PASSWORD_COMMON": (
        "密码过于常见",
        "Password is too common.",
        "密碼過於常見",
    ),
    "TOTP_ALREADY_ENABLED": (
        "二次验证已开启",
        "Two-factor auth is already enabled.",
        "二次驗證已開啟",
    ),
    "TOTP_SEED_REQUIRED": (
        "请先生成二次验证种子",
        "Generate a two-factor seed first.",
        "請先產生二次驗證種子",
    ),
    "ORIGIN_FORBIDDEN": (
        "当前来源地址不被允许访问此接口",
        "This origin is not allowed to access the API.",
        "目前來源位址不被允許存取此介面",
    ),
    "BOOTSTRAP_TOKEN_USED": (
        "初始化口令已被使用，超级管理员应已创建",
        "Bootstrap token was already used; a superadmin should exist.",
        "初始化口令已被使用，超級管理員應已建立",
    ),
    "BOOTSTRAP_TOKEN_MISSING": (
        "初始化口令文件不存在，请先按文档生成",
        "Bootstrap token file is missing. Generate it per the docs.",
        "初始化口令檔不存在，請先依文件產生",
    ),
    "BOOTSTRAP_TOKEN_INVALID": (
        "初始化口令不正确",
        "Bootstrap token is incorrect.",
        "初始化口令不正確",
    ),
    "BOOTSTRAP_ALREADY_DONE": (
        "超级管理员已存在，无需再次初始化",
        "Superadmin already exists; bootstrap is not needed.",
        "超級管理員已存在，無需再次初始化",
    ),
    "ROLE_SUPERADMIN_FORBIDDEN": (
        "不能通过该接口分配超级管理员",
        "Cannot assign superadmin through this API.",
        "不能透過該介面指派超級管理員",
    ),
    "ROLE_NOT_FOUND": (
        "角色不存在",
        "Role not found.",
        "角色不存在",
    ),
    "USER_NOT_FOUND": (
        "用户不存在",
        "User not found.",
        "使用者不存在",
    ),
    "MAIL_SEND_RATE_LIMITED": (
        "发送过于频繁，请稍后再试",
        "Sending too frequently. Try again later.",
        "寄送過於頻繁，請稍後再試",
    ),
    "MAIL_DAILY_LIMIT": (
        "今日发送次数已达上限",
        "Daily send limit reached.",
        "今日寄送次數已達上限",
    ),
    "MAIL_SEND_FAILED": (
        "邮件暂时发不出去，请稍后再试；若持续出现请联系客服",
        "Mail could not be sent. Try again later, or contact support.",
        "郵件暫時寄不出去，請稍後再試；若持續出現請聯絡客服",
    ),
    "TOKEN_TOO_MANY_ATTEMPTS": (
        "尝试验证次数过多，请重新获取新的链接或令牌",
        "Too many verification attempts. Request a new link or token.",
        "嘗試驗證次數過多，請重新取得新的連結或令牌",
    ),
    "TOKEN_EXPIRED": (
        "验证链接或令牌已过期，请重新获取",
        "Verification link or token expired. Request a new one.",
        "驗證連結或令牌已過期，請重新取得",
    ),
    "TOKEN_MISMATCH": (
        "验证码或令牌不正确",
        "Incorrect verification code or token.",
        "驗證碼或令牌不正確",
    ),
    # payments
    "IDEMPOTENCY_KEY_REQUIRED": (
        "请在请求头提供 Idempotency-Key，避免重复下单",
        "Provide an Idempotency-Key header to avoid duplicate orders.",
        "請在請求頭提供 Idempotency-Key，避免重複下單",
    ),
    "IDEMPOTENCY_KEY_REUSED": (
        "重复提交：该幂等键已被使用，请更换后重试",
        "Idempotency key already used. Use a new key and retry.",
        "重複提交：該冪等鍵已被使用，請更換後重試",
    ),
    "IDEMPOTENCY_KEY_INVALID": (
        "请提供合法的 Idempotency-Key（1～80 个字符）",
        "Provide a valid Idempotency-Key (1–80 characters).",
        "請提供合法的 Idempotency-Key（1～80 個字元）",
    ),
    "IDEMPOTENCY_PAYLOAD_MISMATCH": (
        "同一幂等键对应的请求内容不一致，请更换键后重试",
        "Same idempotency key with a different payload. Use a new key.",
        "同一冪等鍵對應的請求內容不一致，請更換鍵後重試",
    ),
    "PRODUCT_NOT_FOUND": (
        "充值套餐不存在",
        "Top-up package not found.",
        "充值套餐不存在",
    ),
    "PRODUCT_DELETED": (
        "充值套餐已删除，不能购买",
        "Top-up package was deleted and cannot be purchased.",
        "充值套餐已刪除，不能購買",
    ),
    "PRODUCT_DISABLED": (
        "充值套餐已停用，暂时不能购买",
        "Top-up package is disabled and cannot be purchased right now.",
        "充值套餐已停用，暫時不能購買",
    ),
    "PRODUCT_CURRENCY_MISMATCH": (
        "该套餐币种与当前结算币不一致，不能购买",
        "Package currency does not match the settlement currency.",
        "該套餐幣種與目前結算幣不一致，不能購買",
    ),
    "ORDER_NOT_FOUND": (
        "订单不存在",
        "Order not found.",
        "訂單不存在",
    ),
    "ORDER_EXPIRED": (
        "订单已过期，请重新下单",
        "Order expired. Create a new one.",
        "訂單已過期，請重新下單",
    ),
    "ORDER_STATUS_FILTER_INVALID": (
        "订单状态「{status}」不支持筛选",
        "Order status 「{status}」 cannot be used as a filter.",
        "訂單狀態「{status}」不支援篩選",
    ),
    "ORDER_CONFIRM_STATUS_INVALID": (
        "订单当前状态为「{status}」，不能再确认",
        "Order status is 「{status}」 and cannot be confirmed again.",
        "訂單目前狀態為「{status}」，不能再確認",
    ),
    "RECONCILE_STATUS_INVALID": (
        "对账状态只能是 unchecked / matched / disputed",
        "Reconcile status must be unchecked, matched, or disputed.",
        "對帳狀態只能是 unchecked / matched / disputed",
    ),
    "RECONCILE_ORDER_NOT_CREDITED": (
        "只有已入账订单（已完成/多付）才能标记对账结果",
        "Only credited orders (completed/overpaid) can be reconciled.",
        "只有已入帳訂單（已完成/多付）才能標記對帳結果",
    ),
    "RECONCILE_CHANNEL_INVALID": (
        "不支持的对账渠道「{channel}」",
        "Unsupported reconcile channel 「{channel}」.",
        "不支援的對帳通路「{channel}」",
    ),
    "MOCK_PAYMENTS_DISABLED": (
        "当前环境未开启模拟支付",
        "Mock payments are disabled in this environment.",
        "目前環境未開啟模擬支付",
    ),
    "MOCK_CHANNEL_REQUIRED": (
        "该订单不是模拟支付渠道，不能用模拟确认",
        "This order is not a mock channel and cannot be mock-confirmed.",
        "該訂單不是模擬支付通路，不能用模擬確認",
    ),
    "REFUND_NOT_FOUND": (
        "退款单不存在",
        "Refund not found.",
        "退款單不存在",
    ),
    "REFUND_ORDER_NOT_CREDITED": (
        "订单状态为「{status}」，尚未入账，不能退款",
        "Order status is 「{status}」 and is not credited; cannot refund.",
        "訂單狀態為「{status}」，尚未入帳，不能退款",
    ),
    "REFUND_USDT_DESTINATION": (
        "USDT 退款只能退回原付款地址",
        "USDT refunds must return to the original payer address.",
        "USDT 退款只能退回原付款位址",
    ),
    "REFUND_ALREADY_EXISTS": (
        "该订单已有退款单，不能重复发起",
        "A refund already exists for this order.",
        "該訂單已有退款單，不能重複發起",
    ),
    "REFUND_NOT_PENDING_REVIEW": (
        "退款单当前状态为「{status}」，不是待复核，不能复核",
        "Refund status is 「{status}」 and is not pending review.",
        "退款單目前狀態為「{status}」，不是待覆核，不能覆核",
    ),
    "REFUND_REJECT_STATUS_INVALID": (
        "退款单当前状态为「{status}」，只能拒绝待复核或已复核待执行的单",
        "Refund status is 「{status}」; only pending or reviewed refunds can be rejected.",
        "退款單目前狀態為「{status}」，只能拒絕待覆核或已覆核待執行的單",
    ),
    "REFUND_SELF_REVIEW_FORBIDDEN": (
        "退款发起人不能复核自己的单，请换另一名财务",
        "The requester cannot review their own refund. Use another finance user.",
        "退款發起人不能覆核自己的單，請換另一名財務",
    ),
    "REFUND_SELF_REJECT_FORBIDDEN": (
        "退款发起人不能拒绝自己的单，请换另一名财务",
        "The requester cannot reject their own refund. Use another finance user.",
        "退款發起人不能拒絕自己的單，請換另一名財務",
    ),
    "REFUND_NOT_REVIEWED": (
        "退款单当前状态为「{status}」，须先完成复核再执行",
        "Refund status is 「{status}」; review it before executing.",
        "退款單目前狀態為「{status}」，須先完成覆核再執行",
    ),
    "REFUND_EXECUTOR_MUST_BE_THIRD": (
        "退款执行人必须是发起人、复核人之外的第三人",
        "The executor must be a third person, not the requester or reviewer.",
        "退款執行人必須是發起人、覆核人之外的第三人",
    ),
    "FX_DEVIATION_TOO_HIGH": (
        "当前汇率偏离过大，已拒绝下单，请稍后再试",
        "FX deviation is too high. Order rejected; try again later.",
        "目前匯率偏離過大，已拒絕下單，請稍後再試",
    ),
    "USDT_ADDRESS_UNCONFIGURED": (
        "USDT 固定收款地址尚未配置，暂时无法下单",
        "USDT payout address is not configured; cannot place the order.",
        "USDT 固定收款位址尚未設定，暫時無法下單",
    ),
    "USDT_TAIL_POOL_FULL": (
        "USDT 尾数池已满，请稍后再试或换其他渠道",
        "USDT tail pool is full. Try again later or use another channel.",
        "USDT 尾數池已滿，請稍後再試或換其他通路",
    ),
    "USDT_AMOUNT_TOO_LOW": (
        "低于 USDT 最低充值金额（当前最低 {min_amount}）",
        "Below the USDT minimum top-up ({min_amount}).",
        "低於 USDT 最低充值金額（目前最低 {min_amount}）",
    ),
    "CHANNEL_NOT_ALLOWED_OVERSEAS": (
        "海外模式不能使用微信/支付宝，请改用 Stripe 或 USDT",
        "Overseas mode cannot use WeChat/Alipay. Use Stripe or USDT.",
        "海外模式不能使用微信/支付寶，請改用 Stripe 或 USDT",
    ),
    "CHANNEL_NOT_ALLOWED_CN": (
        "大陆模式不能使用 Stripe/USDT，请改用微信或支付宝",
        "Mainland mode cannot use Stripe/USDT. Use WeChat or Alipay.",
        "大陸模式不能使用 Stripe/USDT，請改用微信或支付寶",
    ),
    "CHANNEL_UNSUPPORTED": (
        "不支持的支付渠道「{channel}」",
        "Unsupported payment channel 「{channel}」.",
        "不支援的支付通路「{channel}」",
    ),
    "CHANNEL_NOT_CONFIGURED": (
        "「{channel}」支付渠道尚未配置，暂时无法下单",
        "Payment channel 「{channel}」 is not configured.",
        "「{channel}」支付通路尚未設定，暫時無法下單",
    ),
    # keys
    "KEY_NAME_INVALID": (
        "密钥名称需要在 1 到 128 个字符之间",
        "Key name must be 1–128 characters.",
        "金鑰名稱需在 1 到 128 個字元之間",
    ),
    "KEY_STATUS_INVALID": (
        "密钥状态不支持，请使用列表中的状态",
        "Unsupported key status.",
        "金鑰狀態不支援，請使用列表中的狀態",
    ),
    "KEY_NOT_FOUND": (
        "密钥不存在",
        "API key not found.",
        "金鑰不存在",
    ),
    "KEY_EXPIRES_BAD_FORMAT": (
        "到期时间格式不正确，请使用带时区的 ISO 时间",
        "Invalid expiry format. Use ISO datetime with timezone.",
        "到期時間格式不正確，請使用帶時區的 ISO 時間",
    ),
    "KEY_EXPIRES_TZ_REQUIRED": (
        "到期时间必须带时区（例如以 Z 或 +08:00 结尾）",
        "Expiry must include a timezone (e.g. Z or +08:00).",
        "到期時間必須帶時區（例如以 Z 或 +08:00 結尾）",
    ),
    "KEY_BUDGET_BAD_FORMAT": (
        "预算必须是有效的十进制数字",
        "Budget must be a valid decimal number.",
        "預算必須是有效的十進位數字",
    ),
    "KEY_BUDGET_POSITIVE": (
        "预算必须大于 0",
        "Budget must be greater than 0.",
        "預算必須大於 0",
    ),
    "SORT_FIELD_INVALID": (
        "排序字段不支持，请使用列表中的字段名",
        "Unsupported sort field.",
        "排序欄位不支援，請使用列表中的欄位名",
    ),
    "SETTLEMENT_STATUS_INVALID": (
        "结算状态不支持，请使用列表中的状态",
        "Unsupported settlement status.",
        "結算狀態不支援，請使用列表中的狀態",
    ),
    "API_KEY_BAD_FORMAT": (
        "API Key 格式不正确（应以 sk- 开头）",
        "API key format is invalid (must start with sk-).",
        "API Key 格式不正確（應以 sk- 開頭）",
    ),
    "API_KEY_INVALID": (
        "API Key 已失效（可能已吊销或已过期）",
        "API key is invalid (revoked or expired).",
        "API Key 已失效（可能已吊銷或已過期）",
    ),
    "API_KEY_MISSING": (
        "API Key 不存在",
        "API key not found.",
        "API Key 不存在",
    ),
    "API_KEY_REVOKED": (
        "API Key 已删除（吊销），不能再使用",
        "API key was revoked and cannot be used.",
        "API Key 已刪除（吊銷），不能再使用",
    ),
    "API_KEY_EXPIRED": (
        "API Key 已过期",
        "API key has expired.",
        "API Key 已過期",
    ),
    "API_KEY_DISABLED": (
        "API Key 已停用，暂时不能调用；可在控制台重新启用",
        "API key is disabled. Re-enable it in the console.",
        "API Key 已停用，暫時不能呼叫；可在控制台重新啟用",
    ),
    "API_KEY_STATUS_INVALID": (
        "API Key 当前状态为「{status}」，不能使用",
        "API key status is 「{status}」 and cannot be used.",
        "API Key 目前狀態為「{status}」，不能使用",
    ),
    "API_KEY_IP_DENIED": (
        "来源 IP 不在该密钥的白名单中",
        "Source IP is not on this key’s allowlist.",
        "來源 IP 不在該金鑰的白名單中",
    ),
    "API_KEY_BUDGET_EXCEEDED": (
        "该密钥的预算已用完，请提高预算或更换密钥",
        "This key’s budget is exhausted. Raise the budget or use another key.",
        "該金鑰的預算已用完，請提高預算或更換金鑰",
    ),
    "API_KEY_MODEL_DENIED": (
        "该密钥无权调用此模型，请在密钥权限中勾选该模型",
        "This key cannot call that model. Allow it in key permissions.",
        "該金鑰無權呼叫此模型，請在金鑰權限中勾選該模型",
    ),
    "USAGE_NOT_FOUND": (
        "调用记录不存在",
        "Usage record not found.",
        "呼叫記錄不存在",
    ),
}


def inject_backend() -> None:
    path = ROOT / "apps/api/app/core/errors.py"
    text = path.read_text(encoding="utf-8")
    # insert before closing of MESSAGE_BY_CODE dict (after COUPON_EXHAUSTED line)
    marker = '"COUPON_EXHAUSTED": "优惠券兑换名额已用完",\n}'
    if marker not in text:
        raise SystemExit("MESSAGE_BY_CODE end marker missing")
    lines = []
    for code, (zh, _en, _tw) in CATALOG.items():
        if f'"{code}":' in text:
            continue
        lines.append(f'    "{code}": "{zh}",')
    if not lines:
        print("backend: all codes present")
        return
    block = "\n".join(lines) + "\n"
    text = text.replace(marker, '"COUPON_EXHAUSTED": "优惠券兑换名额已用完",\n' + block + "}")
    path.write_text(text, encoding="utf-8")
    print(f"backend +{len(lines)} codes")


def inject_frontend(locale: str, idx: int) -> None:
    """idx: 0=zh-CN in API map unused; for frontend: en=1, zh-CN=0, zh-TW=2 relative to tuple."""
    # tuple is (zh-CN, en, zh-TW)
    map_idx = {"zh-CN": 0, "en": 1, "zh-TW": 2}[locale]
    path = ROOT / f"apps/web/src/content/{locale}.ts"
    text = path.read_text(encoding="utf-8")
    # find end of errors block: last COUPON_EXHAUSTED then },
    probe = "COUPON_EXHAUSTED:"
    start = text.find(probe)
    if start < 0:
        raise SystemExit(f"errors block missing in {locale}")
    end = text.find("\n  },", start)
    if end < 0:
        raise SystemExit(f"errors end missing in {locale}")
    chunk = text[start:end]
    added = 0
    extra = []
    for code, vals in CATALOG.items():
        if f"{code}:" in chunk or f"{code}:" in text[text.find("errors: {"):end]:
            continue
        msg = vals[map_idx].replace("\\", "\\\\").replace('"', '\\"')
        extra.append(f'    {code}: "{msg}",')
        added += 1
    if not extra:
        print(f"{locale}: all present")
        return
    insert = "\n" + "\n".join(extra)
    text = text[:end] + insert + text[end:]
    path.write_text(text, encoding="utf-8")
    print(f"{locale} +{added}")


def wire_components() -> None:
    comp = ROOT / "apps/web/src/components"
    for path in sorted(comp.glob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        if "errorMessage(" not in text:
            continue
        if "useI18n" not in text:
            print(f"skip no i18n {path.name}")
            continue
        orig = text
        if 'from "@/lib/api-client"' in text and "errorMessage" in text:
            # adjust import
            if "apiErrorLabel" not in text:
                if "errorMessage," in text:
                    text = text.replace("errorMessage,", "")
                    text = text.replace("errorMessage ", "")
                text = text.replace(
                    'from "@/lib/api-client";',
                    'from "@/lib/api-client";\nimport { apiErrorLabel } from "@/lib/error-label";',
                )
                # clean empty imports like {  getJson
                text = text.replace("{  ", "{ ")
                text = text.replace("{ ,", "{")
                text = text.replace(", }", " }")
                text = text.replace("{ }", "{}")
            text = text.replace("errorMessage(", "apiErrorLabel(t, ")
            # avoid double t,
            while "apiErrorLabel(t, t," in text:
                text = text.replace("apiErrorLabel(t, t,", "apiErrorLabel(t,")
        if text != orig:
            path.write_text(text, encoding="utf-8")
            print(f"wired {path.name}")
        else:
            print(f"noop {path.name}")


if __name__ == "__main__":
    inject_backend()
    for loc in ("en", "zh-CN", "zh-TW"):
        inject_frontend(loc, 0)
    wire_components()
    print("done")
