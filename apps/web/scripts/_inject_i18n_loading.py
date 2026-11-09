# -*- coding: utf-8 -*-
"""One-shot: inject loading/loadFail after each page lead in admin-*.ts"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "content"

FILES = {
    "en": ROOT / "admin-en.ts",
    "zh-CN": ROOT / "admin-zh-CN.ts",
    "zh-TW": ROOT / "admin-zh-TW.ts",
}

PAGES: dict[str, dict[str, tuple[str, str]]] = {
    "users": {
        "en": ("Loading users…", "Users could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取用户", "暂时读不到用户列表，请刷新后重试"),
        "zh-TW": ("正在讀取使用者", "暫時讀不到使用者列表，請重新整理後重試"),
    },
    "providers": {
        "en": ("Loading providers…", "Providers could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取供应商", "暂时读不到供应商列表，请刷新后重试"),
        "zh-TW": ("正在讀取供應商", "暫時讀不到供應商列表，請重新整理後重試"),
    },
    "models": {
        "en": ("Loading models…", "Models could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取模型", "暂时读不到模型列表，请刷新后重试"),
        "zh-TW": ("正在讀取模型", "暫時讀不到模型列表，請重新整理後重試"),
    },
    "deployments": {
        "en": ("Loading deployments…", "Deployments could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取部署", "暂时读不到部署列表，请刷新后重试"),
        "zh-TW": ("正在讀取部署", "暫時讀不到部署列表，請重新整理後重試"),
    },
    "keys": {
        "en": ("Loading keys…", "Keys could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取密钥", "暂时读不到密钥列表，请刷新后重试"),
        "zh-TW": ("正在讀取金鑰", "暫時讀不到金鑰列表，請重新整理後重試"),
    },
    "orders": {
        "en": ("Loading orders…", "Orders could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取订单", "暂时读不到订单，请刷新后重试"),
        "zh-TW": ("正在讀取訂單", "暫時讀不到訂單，請重新整理後重試"),
    },
    "products": {
        "en": ("Loading packages…", "Packages could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取充值套餐", "暂时读不到充值套餐，请刷新后重试"),
        "zh-TW": ("正在讀取儲值套餐", "暫時讀不到儲值套餐，請重新整理後重試"),
    },
    "refunds": {
        "en": ("Loading refunds…", "Refunds could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取退款", "暂时读不到退款单，请刷新后重试"),
        "zh-TW": ("正在讀取退款", "暫時讀不到退款單，請重新整理後重試"),
    },
    "ledger": {
        "en": ("Loading ledger…", "Ledger could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取账本", "暂时读不到账本，请刷新后重试"),
        "zh-TW": ("正在讀取帳本", "暫時讀不到帳本，請重新整理後重試"),
    },
    "usage": {
        "en": ("Loading usage…", "Usage could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取调用记录", "暂时读不到调用记录，请刷新后重试"),
        "zh-TW": ("正在讀取呼叫記錄", "暫時讀不到呼叫記錄，請重新整理後重試"),
    },
    "crypto": {
        "en": ("Loading crypto ledger…", "Crypto ledger could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取台账", "暂时读不到加密货币台账，请刷新后重试"),
        "zh-TW": ("正在讀取台帳", "暫時讀不到加密貨幣台帳，請重新整理後重試"),
    },
    "health": {
        "en": ("Checking dependencies…", "Health check failed. Try again later."),
        "zh-CN": ("正在检查依赖", "健康检查未成功，请稍后刷新"),
        "zh-TW": ("正在檢查相依服務", "健康檢查未成功，請稍後重新整理"),
    },
    "audit": {
        "en": ("Loading audit log…", "Audit log could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取审计", "暂时读不到审计记录，请刷新后重试"),
        "zh-TW": ("正在讀取稽核", "暫時讀不到稽核記錄，請重新整理後重試"),
    },
    "backups": {
        "en": ("Loading backups…", "Backups could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取备份", "暂时读不到备份列表，请刷新后重试"),
        "zh-TW": ("正在讀取備份", "暫時讀不到備份列表，請重新整理後重試"),
    },
    "announcements": {
        "en": ("Loading announcements…", "Announcements could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取公告", "暂时读不到公告，请刷新后重试"),
        "zh-TW": ("正在讀取公告", "暫時讀不到公告，請重新整理後重試"),
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
    "coupons": {
        "en": ("Loading coupons…", "Coupons could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取优惠券", "暂时读不到优惠券，请刷新后重试"),
        "zh-TW": ("正在讀取優惠券", "暫時讀不到優惠券，請重新整理後重試"),
    },
    "margin": {
        "en": ("Loading margin…", "Margin could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取毛利", "暂时读不到毛利数据，请刷新后重试"),
        "zh-TW": ("正在讀取毛利", "暫時讀不到毛利資料，請重新整理後重試"),
    },
    "content": {
        "en": ("Loading content safety…", "Content safety could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取内容安全", "暂时读不到内容安全记录，请刷新后重试"),
        "zh-TW": ("正在讀取內容安全", "暫時讀不到內容安全記錄，請重新整理後重試"),
    },
    "tasks": {
        "en": ("Loading tasks…", "Tasks could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取任务", "暂时读不到任务，请刷新后重试"),
        "zh-TW": ("正在讀取任務", "暫時讀不到任務，請重新整理後重試"),
    },
    "routes": {
        "en": ("Loading routes…", "Routes could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取路由", "暂时读不到路由，请刷新后重试"),
        "zh-TW": ("正在讀取路由", "暫時讀不到路由，請重新整理後重試"),
    },
    "settings": {
        "en": ("Loading settings…", "Settings could not be loaded. Refresh and try again."),
        "zh-CN": ("正在读取设置", "暂时读不到设置，请刷新后重试"),
        "zh-TW": ("正在讀取設定", "暫時讀不到設定，請重新整理後重試"),
    },
}


def quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def inject(text: str, page: str, loading: str, load_fail: str) -> str:
    # Match from `    page: {` through the lead line
    pattern = re.compile(
        rf"(    {re.escape(page)}: \{{\n(?:      .*\n)*?      lead: .*?\n)",
        re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return text
    window = text[m.start() : m.end() + 160]
    if "loading:" in window:
        return text
    insert = f"      loading: {quote(loading)},\n      loadFail: {quote(load_fail)},\n"
    return text[: m.end()] + insert + text[m.end() :]


def main() -> None:
    for locale, path in FILES.items():
        text = path.read_text(encoding="utf-8")
        for page, locs in PAGES.items():
            loading, load_fail = locs[locale]
            before = text
            text = inject(text, page, loading, load_fail)
            status = "OK" if text != before else "SKIP/MISS"
            print(f"{status} {locale} {page}")
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
