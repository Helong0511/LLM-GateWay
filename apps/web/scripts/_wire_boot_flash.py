# -*- coding: utf-8 -*-
"""Wire useBootFlash + loading/loadFail into admin/console panels."""
from __future__ import annotations

import re
from pathlib import Path

COMP = Path(__file__).resolve().parents[1] / "src" / "components"

# file -> (loading_expr, loadFail_default used in errorMessage fallback)
BOOT: list[tuple[str, str, str, str]] = [
    # file, loading expr, chinese loading to find, chinese loadFail fallback
    ("admin-providers.tsx", "t.admin.pages.providers.loading", "正在读取供应商", "暂时读不到供应商列表，请刷新后重试"),
    ("admin-users.tsx", "t.admin.pages.users.loading", "正在读取用户", "暂时读不到用户列表，请刷新后重试"),
    ("admin-models.tsx", "t.admin.pages.models.loading", "正在读取模型", "暂时读不到模型列表，请刷新后重试"),
    ("admin-deployments.tsx", "t.admin.pages.deployments.loading", "正在读取部署", "暂时读不到部署列表，请刷新后重试"),
    ("admin-keys.tsx", "t.admin.pages.keys.loading", "正在读取密钥", "暂时读不到密钥列表，请刷新后重试"),
    ("admin-orders.tsx", "t.admin.pages.orders.loading", "正在读取订单", "暂时读不到订单，请刷新后重试"),
    ("admin-products.tsx", "t.admin.pages.products.loading", "正在读取充值套餐", "暂时读不到充值套餐，请刷新后重试"),
    ("admin-refunds.tsx", "t.admin.pages.refunds.loading", "正在读取退款", "暂时读不到退款单，请刷新后重试"),
    ("admin-ledger.tsx", "t.admin.pages.ledger.loading", "正在读取账本", "暂时读不到账本，请刷新后重试"),
    ("admin-usage.tsx", "t.admin.pages.usage.loading", "正在读取调用记录", "暂时读不到调用记录，请刷新后重试"),
    ("admin-crypto.tsx", "t.admin.pages.crypto.loading", "正在读取台账", "暂时读不到加密货币台账，请刷新后重试"),
    ("admin-health.tsx", "t.admin.pages.health.loading", "正在检查依赖", "健康检查未成功，请稍后刷新"),
    ("admin-audit.tsx", "t.admin.pages.audit.loading", "正在读取审计", "暂时读不到审计记录，请刷新后重试"),
    ("keys-panel.tsx", "t.console.keys.loading", "正在读取密钥", "暂时读不到密钥列表，请刷新后重试"),
    ("usage-panel.tsx", "t.console.usage.loading", "正在读取调用记录", "暂时读不到调用记录，请刷新后重试"),
    ("models-panel.tsx", "t.console.models.loading", "正在读取已上架模型", "暂时读不到模型目录，请刷新后重试"),
    ("account-panel.tsx", "t.console.account.loading", "正在读取账号", "暂时读不到账号信息，请重新登录或刷新页面"),
    ("profile-panel.tsx", "t.console.profile.loading", "正在读取资料", "暂时读不到个人资料，请刷新后重试"),
    ("security-panel.tsx", "t.console.security.loading", "正在读取会话", "暂时读不到安全信息，请刷新后重试"),
    ("billing-panel.tsx", "t.console.billing.loading", "正在读取账单", "暂时读不到账单信息，请刷新后重试"),
]


def ensure_imports(text: str) -> str:
    if "useBootFlash" not in text:
        # after useI18n import if present
        if 'from "@/components/locale-provider"' in text:
            text = text.replace(
                'from "@/components/locale-provider";',
                'from "@/components/locale-provider";\nimport { useBootFlash } from "@/lib/boot-flash";',
                1,
            )
        else:
            text = 'import { useBootFlash } from "@/lib/boot-flash";\n' + text
    # remove unused infoFlash from import if only used for boot - keep if still used
    return text


def wire(path: Path, loading_expr: str, zh_loading: str, zh_fail: str) -> None:
    text = path.read_text(encoding="utf-8")
    if "useBootFlash" in text and f"infoFlash(\"{zh_loading}\")" not in text:
        print("SKIP already", path.name)
        return
    text = ensure_imports(text)

    # Replace useState flash init
    old = f'useState<FlashMessage | null>(infoFlash("{zh_loading}"))'
    new = None
    if old in text:
        # Pattern: const [flash, setFlash] = useState...
        text = text.replace(
            f"const [flash, setFlash] = {old}",
            f"const {{ flash, setFlash }} = useBootFlash({loading_expr})",
            1,
        )
        # If that didn't work because of spacing
        if f'infoFlash("{zh_loading}")' in text:
            text = re.sub(
                rf"const \[flash, setFlash\] = useState<FlashMessage \| null>\(infoFlash\(\"{re.escape(zh_loading)}\"\)\);",
                f"const {{ flash, setFlash }} = useBootFlash({loading_expr});",
                text,
                count=1,
            )
    else:
        print("MISS init", path.name, zh_loading)

    # Replace errorMessage(..., "zh_fail") with loadFail - only first occurrence in pull* helpers often
    if zh_fail in text:
        # find loadFail key from loading_expr
        # t.admin.pages.providers.loading -> t.admin.pages.providers.loadFail
        fail_expr = loading_expr.replace(".loading", ".loadFail")
        text = text.replace(f'errorMessage(result.envelope, "{zh_fail}")', f"errorMessage(result.envelope, {fail_expr})", 1)
        # also sessionResult etc
        text = text.replace(f'errorMessage(sessionResult.envelope, "{zh_fail}")', f"errorMessage(sessionResult.envelope, {fail_expr})", 1)

    # Remove unused FlashMessage import pieces carefully - leave as is
    # Remove infoFlash from import if unused
    if "infoFlash(" not in text and "infoFlash," in text:
        text = text.replace("infoFlash,\n", "").replace("infoFlash, ", "")

    # FlashMessage type may still be needed - keep
    if "FlashMessage" in text and "useState<FlashMessage" not in text and ": FlashMessage" not in text:
        # might still use FlashMessage in props - keep
        pass

    path.write_text(text, encoding="utf-8")
    print("OK", path.name)


def main() -> None:
    for name, loading, zh_loading, zh_fail in BOOT:
        wire(COMP / name, loading, zh_loading, zh_fail)


if __name__ == "__main__":
    main()
