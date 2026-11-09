# -*- coding: utf-8 -*-
"""Fix module-level pull* helpers that incorrectly reference `t`."""
from __future__ import annotations

import re
from pathlib import Path

COMP = Path(__file__).resolve().parents[1] / "src" / "components"

# (file, fn_name, t_expr for loadFail, how to find calls — 'simple' | 'filters' | 'params_obj' | 'billing')
SPECS: list[tuple[str, str, str, str]] = [
    ("admin-providers.tsx", "pullProviders", "t.admin.pages.providers.loadFail", "simple"),
    ("admin-models.tsx", "pullModels", "t.admin.pages.models.loadFail", "simple"),
    ("admin-deployments.tsx", "pullDeployments", "t.admin.pages.deployments.loadFail", "simple"),
    ("admin-products.tsx", "pullProducts", "t.admin.pages.products.loadFail", "simple"),
    ("admin-refunds.tsx", "pullRefunds", "t.admin.pages.refunds.loadFail", "simple"),
    ("admin-ledger.tsx", "pullLedger", "t.admin.pages.ledger.loadFail", "simple"),
    ("admin-usage.tsx", "pullUsage", "t.admin.pages.usage.loadFail", "simple"),
    ("admin-health.tsx", "pullHealth", "t.admin.pages.health.loadFail", "simple"),
    ("admin-audit.tsx", "pullEvents", "t.admin.pages.audit.loadFail", "simple"),
    ("keys-panel.tsx", "pullKeys", "t.console.keys.loadFail", "simple"),
    ("admin-users.tsx", "pullUsers", "t.admin.pages.users.loadFail", "filters"),
    ("admin-orders.tsx", "pullOrders", "t.admin.pages.orders.loadFail", "filters"),
    ("admin-keys.tsx", "pullKeys", "t.admin.pages.keys.loadFail", "filters"),
    ("admin-crypto.tsx", "pullCrypto", "t.admin.pages.crypto.loadFail", "params_obj"),
    ("billing-panel.tsx", "pullBilling", "t.console.billing.loadFail", "billing"),
    ("security-panel.tsx", "pullSecurity", "t.console.security.loadFail", "simple"),
]


def replace_once(text: str, old: str, new: str) -> tuple[str, bool]:
    if old not in text:
        return text, False
    return text.replace(old, new, 1), True


def fix(path: Path, fn: str, t_expr: str, kind: str) -> None:
    text = path.read_text(encoding="utf-8")
    # Replace t.xxx with loadFail in errorMessage (all occurrences of this t_expr for result)
    text2 = text.replace(f"errorMessage(result.envelope, {t_expr})", "errorMessage(result.envelope, loadFail)")
    text2 = text2.replace(f"errorMessage(sessionResult.envelope, {t_expr})", "errorMessage(sessionResult.envelope, loadFail)")
    if text2 == text and t_expr in text:
        print("WARN no errorMessage replace", path.name)
    text = text2

    if "loadFail: string" in text and f"function {fn}" in text:
        # may already be partially fixed
        pass

    # Patch function signature to add loadFail
    if kind == "simple":
        # async function pullX():  OR async function pullX(page: number):
        patterns = [
            (rf"async function {fn}\(\)", f"async function {fn}(loadFail: string)"),
            (rf"async function {fn}\(page: number\)", f"async function {fn}(page: number, loadFail: string)"),
            (rf"async function {fn}\(pageNo: number\)", f"async function {fn}(pageNo: number, loadFail: string)"),
        ]
        for old, new in patterns:
            text, ok = (lambda t, o, n: (re.sub(o, n, t, count=1), bool(re.search(o, t))))(text, old, new)
            # fix the above broken lambda - do properly:
        for old, new in patterns:
            if re.search(old, text) and "loadFail: string" not in re.search(rf"async function {fn}\([^)]*\)", text).group(0):  # type: ignore
                text = re.sub(old, new, text, count=1)
                break
        else:
            # check if already has loadFail
            m = re.search(rf"async function {fn}\(([^)]*)\)", text)
            if m and "loadFail" not in m.group(1):
                print("MISS simple sig", path.name, fn, m.group(0))
    elif kind == "filters":
        # multi-line: page, filters: {...}
        m = re.search(
            rf"async function {fn}\(\s*page: number,\s*filters: \{{[^}}]+\}}\s*\)",
            text,
        )
        if m and "loadFail" not in m.group(0):
            text = text[: m.end() - 1] + ", loadFail: string)" + text[m.end() :]
        elif not m:
            # admin-keys may differ
            m2 = re.search(rf"async function {fn}\(([\s\S]*?)\): Promise", text)
            if m2 and "loadFail" not in m2.group(1):
                inner = m2.group(1).rstrip()
                text = text[: m2.start(1)] + inner + ", loadFail: string" + text[m2.end(1) :]
            else:
                print("MISS filters sig", path.name, fn)
    elif kind == "params_obj":
        m = re.search(rf"async function {fn}\(params: \{{[\s\S]*?\}}\)", text)
        if m and "loadFail" not in m.group(0):
            text = text[: m.end() - 1] + ", loadFail: string)" + text[m.end() :]
        else:
            print("MISS params sig", path.name)
    elif kind == "billing":
        old = "async function pullBilling(entryPage: number, orderPage: number)"
        new = "async function pullBilling(entryPage: number, orderPage: number, loadFail: string)"
        if old in text:
            text = text.replace(old, new, 1)

    # Update call sites — file-specific heuristics
    if kind == "simple":
        # pullX() -> pullX(t_expr)
        text = re.sub(rf"\b{fn}\(\)", f"{fn}({t_expr})", text)
        # pullX(page) / pullX(pageNo) but not definition
        text = re.sub(
            rf"(?<!function )\b{fn}\((page(?:No)?)\)",
            rf"{fn}(\1, {t_expr})",
            text,
        )
        # Avoid double-arg on definition: async function pullX(loadFail: string, t.xxx) 
        text = re.sub(
            rf"async function {fn}\(loadFail: string, {re.escape(t_expr)}\)",
            f"async function {fn}(loadFail: string)",
            text,
        )
        text = re.sub(
            rf"async function {fn}\((page(?:No)?: number), {re.escape(t_expr)}\)",
            rf"async function {fn}(\1, loadFail: string)",
            text,
        )
    elif kind == "filters":
        # pullX(page, { ... }) — multiline object
        # Replace closing of call: look for pullX(page, { applied... })
        # Common patterns in these files:
        patterns_call = [
            # pullUsers(page, { q: appliedQ, status: appliedStatus })
            (
                rf"\b{fn}\((page), (\{{[^}}]+\}})\)",
                rf"{fn}(\1, \2, {t_expr})",
            ),
        ]
        for old, new in patterns_call:
            text = re.sub(old, new, text)
        # multiline filters in pullOrders(page, {\n ... })
        text = re.sub(
            rf"\b{fn}\(\s*(page),\s*(\{{[\s\S]*?\}})\s*\)",
            lambda m: m.group(0)
            if t_expr in m.group(0) or "loadFail" in m.group(0)
            else f"{fn}({m.group(1)}, {m.group(2)}, {t_expr})",
            text,
        )
        # Fix definition corrupted
        text = re.sub(
            rf"(async function {fn}\([\s\S]*?loadFail: string), {re.escape(t_expr)}\)",
            r"\1)",
            text,
        )
    elif kind == "params_obj":
        text = re.sub(
            rf"\b{fn}\((\{{[\s\S]*?\}})\)",
            lambda m: m.group(0)
            if t_expr in m.group(0)
            else f"{fn}({m.group(1)}, {t_expr})",
            text,
            count=3,
        )
        text = re.sub(
            rf"(async function {fn}\(params: \{{[\s\S]*?\}}, loadFail: string), {re.escape(t_expr)}\)",
            r"\1)",
            text,
        )
    elif kind == "billing":
        text = re.sub(
            rf"\b{fn}\((entryPage), (orderPage)\)",
            rf"{fn}(\1, \2, {t_expr})",
            text,
        )
        text = re.sub(
            rf"async function {fn}\(entryPage: number, orderPage: number, loadFail: string, {re.escape(t_expr)}\)",
            f"async function {fn}(entryPage: number, orderPage: number, loadFail: string)",
            text,
        )

    path.write_text(text, encoding="utf-8")
    print("OK", path.name, fn)


def main() -> None:
    for file, fn, t_expr, kind in SPECS:
        fix(COMP / file, fn, t_expr, kind)


if __name__ == "__main__":
    main()
