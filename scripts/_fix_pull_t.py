# -*- coding: utf-8 -*-
"""In module-level pull helpers, replace apiErrorLabel(t, ...) with errorMessage(...)."""
from __future__ import annotations

import re
from pathlib import Path

COMP = Path(r"e:/ZZZ/apps/web/src/components")

# Files reported by tsc
TARGETS = [
    "admin-audit.tsx",
    "admin-crypto.tsx",
    "admin-deployments.tsx",
    "admin-health.tsx",
    "admin-keys.tsx",
    "admin-ledger.tsx",
    "admin-models.tsx",
    "admin-orders.tsx",
    "admin-products.tsx",
    "admin-providers.tsx",
    "admin-refunds.tsx",
    "admin-usage.tsx",
    "admin-users.tsx",
    "billing-panel.tsx",
    "keys-panel.tsx",
    "notifications-panel.tsx",
    "security-panel.tsx",
]


def ensure_error_message_import(text: str) -> str:
    if "errorMessage" in text and re.search(r"\berrorMessage\b", text.split("from \"@/lib/api-client\"")[0] if "from \"@/lib/api-client\"" in text else ""):
        # check import line
        pass
    m = re.search(r'import \{([^}]+)\} from "@/lib/api-client";', text)
    if not m:
        return text
    names = [x.strip() for x in m.group(1).split(",") if x.strip()]
    if "errorMessage" not in names:
        names.insert(0, "errorMessage")
        text = text[: m.start(1)] + " " + ", ".join(names) + " " + text[m.end(1) :]
    return text


def fix_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    orig = text
    # Only replace apiErrorLabel(t, X, Y) that appear BEFORE first "export function" / "export default"
    # Actually safer: replace only inside async function pull* blocks before component exports.
    # Simplest: replace the specific pattern in return/message lines that use loadFail
    text2 = re.sub(
        r"apiErrorLabel\(t,\s*([a-zA-Z0-9_.]+)\.envelope,\s*loadFail\)",
        r"errorMessage(\1.envelope, loadFail)",
        text,
    )
    # also sessionResult etc
    text2 = re.sub(
        r"apiErrorLabel\(t,\s*([a-zA-Z0-9_]+Result)\.envelope,\s*loadFail\)",
        r"errorMessage(\1.envelope, loadFail)",
        text2,
    )
    if text2 != text:
        text2 = ensure_error_message_import(text2)
        path.write_text(text2, encoding="utf-8")
        print("fixed", path.name)
    elif text != orig:
        path.write_text(text, encoding="utf-8")
        print("changed?", path.name)
    else:
        # try broader: any apiErrorLabel(t in lines containing loadFail
        lines = text.splitlines()
        out = []
        changed = False
        for line in lines:
            if "loadFail" in line and "apiErrorLabel(t," in line:
                line = re.sub(
                    r"apiErrorLabel\(t,\s*([^,]+),\s*loadFail\)",
                    r"errorMessage(\1, loadFail)",
                    line,
                )
                changed = True
            out.append(line)
        if changed:
            text2 = "\n".join(out) + ("\n" if text.endswith("\n") else "")
            text2 = ensure_error_message_import(text2)
            path.write_text(text2, encoding="utf-8")
            print("fixed-broad", path.name)
        else:
            print("noop", path.name)


def main() -> None:
    for name in TARGETS:
        fix_file(COMP / name)


if __name__ == "__main__":
    main()
