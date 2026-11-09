# -*- coding: utf-8 -*-
"""Inject loading/loadFail into console sections in en/zh-CN/zh-TW."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "content"
FILES = {
    "en": ROOT / "en.ts",
    "zh-CN": ROOT / "zh-CN.ts",
    "zh-TW": ROOT / "zh-TW.ts",
}

SECTIONS: dict[str, dict[str, tuple[str, str]]] = {
    "billing": {
        "en": ("Loading billing…", "Billing could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取账单", "暂时读不到账单信息，请刷新后重试"),
        "zh-TW": ("正在讀取帳單", "暫時讀不到帳單資訊，請重新整理後重試"),
    },
    "keys": {
        "en": ("Loading keys…", "Keys could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取密钥", "暂时读不到密钥列表，请刷新后重试"),
        "zh-TW": ("正在讀取金鑰", "暫時讀不到金鑰列表，請重新整理後重試"),
    },
    "models": {
        "en": ("Loading published models…", "Models could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取已上架模型", "暂时读不到模型目录，请刷新后重试"),
        "zh-TW": ("正在讀取已上架模型", "暫時讀不到模型目錄，請重新整理後重試"),
    },
    "usage": {
        "en": ("Loading usage…", "Usage could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取调用记录", "暂时读不到调用记录，请刷新后重试"),
        "zh-TW": ("正在讀取呼叫記錄", "暫時讀不到呼叫記錄，請重新整理後重試"),
    },
    "security": {
        "en": ("Loading sessions…", "Security info could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取会话", "暂时读不到安全信息，请刷新后重试"),
        "zh-TW": ("正在讀取工作階段", "暫時讀不到安全資訊，請重新整理後重試"),
    },
    "profile": {
        "en": ("Loading profile…", "Profile could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取资料", "暂时读不到个人资料，请刷新后重试"),
        "zh-TW": ("正在讀取資料", "暫時讀不到個人資料，請重新整理後重試"),
    },
    "account": {
        "en": ("Loading account…", "Account could not be loaded. Sign in again or refresh."),
        "zh-CN": ("正在读取账号", "暂时读不到账号信息，请重新登录或刷新页面"),
        "zh-TW": ("正在讀取帳號", "暫時讀不到帳號資訊，請重新登入或重新整理頁面"),
    },
    "coupons": {
        "en": ("Loading coupons…", "Redemptions could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取优惠券", "暂时读不到兑换记录，请刷新页面重试"),
        "zh-TW": ("正在讀取優惠券", "暫時讀不到兌換記錄，請重新整理頁面重試"),
    },
    "tickets": {
        "en": ("Loading tickets…", "Tickets could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取工单", "暂时读不到工单，请刷新后重试"),
        "zh-TW": ("正在讀取工單", "暫時讀不到工單，請重新整理後重試"),
    },
    "invoices": {
        "en": ("Loading invoices…", "Invoices could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取发票", "暂时读不到发票申请，请刷新后重试"),
        "zh-TW": ("正在讀取發票", "暫時讀不到發票申請，請重新整理後重試"),
    },
}


def quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def inject(text: str, section: str, loading: str, load_fail: str) -> str:
    # Only inside console: { ... }
    console_m = re.search(r"\n  console: \{", text)
    if not console_m:
        return text
    # Find section after console start
    start = console_m.start()
    pattern = re.compile(
        rf"(    {re.escape(section)}: \{{\n(?:      .*\n)*?      lead: .*?\n)",
    )
    m = pattern.search(text, start)
    if not m:
        # account may not have lead first - try title
        pattern2 = re.compile(
            rf"(    {re.escape(section)}: \{{\n(?:      .*\n)*?      title: .*?\n)",
        )
        m = pattern2.search(text, start)
    if not m:
        return text
    window = text[m.start() : m.end() + 120]
    if "loading:" in window and section != "notifications":
        # notifications already has loading - skip if duplicate
        if re.search(r"\n\s+loading:", window):
            return text
    if re.search(r"\n\s+loading:", text[m.start() : m.end() + 80]):
        return text
    insert = f"      loading: {quote(loading)},\n      loadFail: {quote(load_fail)},\n"
    return text[: m.end()] + insert + text[m.end() :]


def main() -> None:
    for locale, path in FILES.items():
        text = path.read_text(encoding="utf-8")
        for section, locs in SECTIONS.items():
            loading, load_fail = locs[locale]
            before = text
            text = inject(text, section, loading, load_fail)
            print(("OK" if text != before else "SKIP/MISS"), locale, section)
        # models.publishedOnly note
        note = {
            "en": "Only published models are listed. Unconfirmed capabilities stay unconfirmed; prices are hidden here.",
            "zh-CN": "只显示已上架模型。没有填写的能力保持为未确认，这里不展示价格。",
            "zh-TW": "只顯示已上架模型。未填寫的能力保持為未確認，這裡不展示價格。",
        }[locale]
        if "publishedOnly:" not in text:
            text2 = inject_extra(text, "models", "publishedOnly", note)
            if text2 != text:
                print("OK", locale, "models.publishedOnly")
                text = text2
        path.write_text(text, encoding="utf-8")


def inject_extra(text: str, section: str, key: str, value: str) -> str:
    console_m = re.search(r"\n  console: \{", text)
    if not console_m:
        return text
    pattern = re.compile(rf"(    {re.escape(section)}: \{{\n)")
    m = pattern.search(text, console_m.start())
    if not m:
        return text
    if f"{key}:" in text[m.end() : m.end() + 400]:
        return text
    insert = f"      {key}: {quote(value)},\n"
    return text[: m.end()] + insert + text[m.end() :]


if __name__ == "__main__":
    main()
