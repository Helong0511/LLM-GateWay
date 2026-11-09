# -*- coding: utf-8 -*-
"""Append msg keys to admin locales and apply string replacements in components.

Idempotent-ish: skips if target already contains the replacement snippet.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"e:\ZZZ\apps\web\src")
CONTENT = ROOT / "content"
COMP = ROOT / "components"

# (file, list of (old, new)) — old must be unique exact substring
REPLACES: dict[str, list[tuple[str, str]]] = {
    "admin-models.tsx": [
        (
            '<span className="mt-0.5 block text-xs text-foreground/60">结算币金额；发布后生成新价格版本，历史调用仍用旧版。</span>',
            '<span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.models.inputPriceHint}</span>',
        ),
        (
            '<span className="mt-0.5 block text-xs text-foreground/60">同上，按输出 token 计费。</span>',
            '<span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.models.outputPriceHint}</span>',
        ),
        (
            '.map((row) => `${String(row.version)} · ${row.active === true ? "生效中" : "历史"} · ${String(row.currency)}`)',
            ".map((row) => `${String(row.version)} · ${row.active === true ? t.admin.pages.models.priceActive : t.admin.pages.models.priceHistory} · ${String(row.currency)}`)",
        ),
        (
            'setFlash(resultFlash(result.ok, "模型已上架。", errorMessage(result.envelope, "模型上架未成功，请核对后重试")));',
            "setFlash(resultFlash(result.ok, t.admin.pages.models.msg.published, errorMessage(result.envelope, t.admin.pages.models.msg.publishFail)));",
        ),
        (
            'setFlash(resultFlash(result.ok, "价格版本已发布。历史调用仍使用原来的快照。", errorMessage(result.envelope, "价格发布未成功，请核对单价后重试")));',
            "setFlash(resultFlash(result.ok, t.admin.pages.models.msg.pricePublished, errorMessage(result.envelope, t.admin.pages.models.msg.pricePublishFail)));",
        ),
        (
            'setFlash(errFlash(errorMessage(result.envelope, "暂时读不到价格版本，请刷新后重试")));',
            "setFlash(errFlash(errorMessage(result.envelope, t.admin.pages.models.msg.priceLoadFail)));",
        ),
        (
            'setFlash(warnFlash("该模型还没有价格版本。"))',
            "setFlash(warnFlash(t.admin.pages.models.msg.noPrice))",
        ),
    ],
    "admin-refunds.tsx": [
        (
            'placeholder="链上哈希，可空"',
            "placeholder={t.admin.pages.refunds.txHashPlaceholder}",
        ),
    ],
    "profile-panel.tsx": [
        (
            'setFlash(resultFlash(result.ok, "资料已保存。", errorMessage(result.envelope, "资料保存未成功，请核对后重试")));',
            "setFlash(resultFlash(result.ok, t.console.profile.saved, errorMessage(result.envelope, t.console.profile.saveFail)));",
        ),
    ],
    "account-panel.tsx": [
        (
            'setFlash(errFlash(errorMessage(result.envelope, "登录状态已失效，请重新登录")));',
            "setFlash(errFlash(errorMessage(result.envelope, t.console.account.sessionExpired)));",
        ),
        (
            'setFlash(errFlash("暂时读不到账号信息，请重新登录或刷新页面"));',
            "setFlash(errFlash(t.console.account.loadFail));",
        ),
    ],
}


MSG_MODELS_EN = """
      inputPriceHint: "Settlement-currency amount; publishing creates a new price version; history keeps the old snapshot.",
      outputPriceHint: "Same currency; billed per output token.",
      priceActive: "Active",
      priceHistory: "History",
      msg: {
        published: "Model published.",
        publishFail: "Publish failed. Check and try again.",
        pricePublished: "Price version published. Historical calls keep the previous snapshot.",
        pricePublishFail: "Price publish failed. Check unit prices.",
        priceLoadFail: "Price versions could not be loaded. Refresh and try again.",
        noPrice: "This model has no price versions yet.",
        confirmUnpublish: "Unpublish 「{name}」?\\n\\nCatalog row is kept; related deployments are disabled.\\nIt leaves the Published/Pending list and cannot be called.",
        unpublished: "Model unpublished and removed from the current list. Switch to Unpublished above to view it.",
        unpublishFail: "Unpublish failed. Refresh and try again.",
      },
"""

MSG_MODELS_CN = """
      inputPriceHint: "结算币金额；发布后生成新价格版本，历史调用仍用旧版。",
      outputPriceHint: "同上，按输出 token 计费。",
      priceActive: "生效中",
      priceHistory: "历史",
      msg: {
        published: "模型已上架。",
        publishFail: "模型上架未成功，请核对后重试",
        pricePublished: "价格版本已发布。历史调用仍使用原来的快照。",
        pricePublishFail: "价格发布未成功，请核对单价后重试",
        priceLoadFail: "暂时读不到价格版本，请刷新后重试",
        noPrice: "该模型还没有价格版本。",
        confirmUnpublish: "确认下架「{name}」？\\n\\n不会物理删除目录记录；关联部署也会停用。\\n下架后不可再调用，并会从当前「上架/待上架」列表移出。",
        unpublished: "模型已下架，已移出当前列表。可在上方切换到「已下架」查看。",
        unpublishFail: "模型下架未成功，请刷新后重试",
      },
"""

MSG_MODELS_TW = """
      inputPriceHint: "結算幣金額；發佈後產生新價格版本，歷史呼叫仍用舊版。",
      outputPriceHint: "同上，按輸出 token 計費。",
      priceActive: "生效中",
      priceHistory: "歷史",
      msg: {
        published: "模型已上架。",
        publishFail: "模型上架未成功，請核對後重試",
        pricePublished: "價格版本已發佈。歷史呼叫仍使用原來的快照。",
        pricePublishFail: "價格發佈未成功，請核對單價後重試",
        priceLoadFail: "暫時讀不到價格版本，請重新整理後重試",
        noPrice: "該模型還沒有價格版本。",
        confirmUnpublish: "確認下架「{name}」？\\n\\n不會實體刪除目錄記錄；關聯部署也會停用。\\n下架後不可再呼叫，並會從目前「上架/待上架」列表移出。",
        unpublished: "模型已下架，已移出目前列表。可在上方切換到「已下架」查看。",
        unpublishFail: "模型下架未成功，請重新整理後重試",
      },
"""


def inject_before(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    if "inputPriceHint:" in text and path.name.startswith("admin"):
        # models already injected?
        if "priceActive:" in text:
            print("SKIP inject", path.name)
            return
    if marker not in text:
        print("MISS marker", path.name, marker[:40])
        return
    # Insert before emptyActive of models or before closing of models - use marker "emptyActive" after stream for models
    text = text.replace(marker, block + marker, 1)
    path.write_text(text, encoding="utf-8")
    print("INJECT", path.name)


def main() -> None:
    # Inject model hints before emptyActive in models pages
    inject_before(
        CONTENT / "admin-en.ts",
        '      emptyActive: "No published or pending models.',
        MSG_MODELS_EN,
    )
    inject_before(
        CONTENT / "admin-zh-CN.ts",
        '      emptyActive: "当前没有上架或待上架的模型。',
        MSG_MODELS_CN,
    )
    inject_before(
        CONTENT / "admin-zh-TW.ts",
        '      emptyActive: "目前沒有上架或待上架的模型。',
        MSG_MODELS_TW,
    )

    # console profile/account keys
    for locale, saved, save_fail, session in [
        ("en.ts", "Profile saved.", "Profile could not be saved. Check and try again.", "Session expired. Please sign in again."),
        ("zh-CN.ts", "资料已保存。", "资料保存未成功，请核对后重试", "登录状态已失效，请重新登录"),
        ("zh-TW.ts", "資料已儲存。", "資料儲存未成功，請核對後重試", "登入狀態已失效，請重新登入"),
    ]:
        path = CONTENT / locale
        text = path.read_text(encoding="utf-8")
        if "saved:" not in text.split("profile:")[1][:400] if "profile:" in text else True:
            text2 = text
            if 'profile: {' in text2 and "saved:" not in text2[text2.find("profile:"): text2.find("profile:") + 500]:
                text2 = text2.replace(
                    "    profile: {\n",
                    f'    profile: {{\n      saved: "{saved}",\n      saveFail: "{save_fail}",\n',
                    1,
                )
            if "sessionExpired:" not in text2:
                text2 = text2.replace(
                    "    account: {\n",
                    f'    account: {{\n      sessionExpired: "{session}",\n',
                    1,
                )
            if text2 != text:
                path.write_text(text2, encoding="utf-8")
                print("OK console keys", locale)
            else:
                print("SKIP console", locale)

    for name, pairs in REPLACES.items():
        path = COMP / name
        text = path.read_text(encoding="utf-8")
        n = 0
        for old, new in pairs:
            if old in text:
                text = text.replace(old, new, 1)
                n += 1
            elif new[:40] in text:
                pass
            else:
                print("MISS", name, old[:60])
        path.write_text(text, encoding="utf-8")
        print(f"OK {name} {n}/{len(pairs)}")


if __name__ == "__main__":
    main()
