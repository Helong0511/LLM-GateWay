# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from pathlib import Path

COMP = Path(r"e:\ZZZ\apps\web\src\components")

# file -> (regex for broken errorMessage line fragment using t., replacement uses loadFail)
# and call_arg to append at call sites

def process(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    export = re.search(r"^export function ", text, re.M)
    if not export:
        return
    head = text[: export.start()]
    body = text[export.start() :]

    # Find t.admin.pages.XXX.loadFail or t.console.XXX.loadFail in head
    refs = re.findall(r"t\.(?:admin\.pages|console)\.[\w.]+\.loadFail", head)
    if not refs:
        return
    # unique
    refs = list(dict.fromkeys(refs))
    if len(refs) != 1:
        print("MULTI", path.name, refs)
        return
    t_expr = refs[0]
    head = head.replace(t_expr, "loadFail")

    # Find the async function that contains loadFail now and add param
    # Get last async function before export (the pull helper)
    funcs = list(re.finditer(r"async function (\w+)\(", head))
    if not funcs:
        print("NO FN", path.name)
        return
    # find which function body contains loadFail
    target_fn = None
    for i, m in enumerate(funcs):
        start = m.start()
        end = funcs[i + 1].start() if i + 1 < len(funcs) else len(head)
        chunk = head[start:end]
        if "loadFail" in chunk and "errorMessage" in chunk:
            target_fn = m.group(1)
            # insert param before matching close paren of signature
            # signature may be multi-line until ): Promise or ): {
            sig_end = re.search(r"\)\s*(?::\s*Promise|:?\s*\{)", chunk)
            if not sig_end:
                print("NO SIG END", path.name, target_fn)
                break
            abs_sig_close = start + sig_end.start()
            # params between m.end()-1... wait m ends after (
            param_region = head[m.end() : abs_sig_close]
            if "loadFail: string" not in param_region:
                insert_at = abs_sig_close
                if param_region.strip():
                    head = head[:insert_at] + ", loadFail: string" + head[insert_at:]
                else:
                    head = head[:insert_at] + "loadFail: string" + head[insert_at:]
            break
    if not target_fn:
        print("NO TARGET", path.name)
        return

    # Update call sites in body: target_fn(...)
    # Use a paren matcher
    def add_arg_to_calls(src: str, fn: str, arg: str) -> str:
        out = []
        i = 0
        while True:
            m = re.search(rf"\b{fn}\(", src[i:])
            if not m:
                out.append(src[i:])
                break
            start = i + m.start()
            open_paren = i + m.end() - 1
            # skip if this is somehow a definition (shouldn't be in body)
            out.append(src[i:start])
            # find matching close
            depth = 0
            j = open_paren
            while j < len(src):
                ch = src[j]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            inner = src[open_paren + 1 : j]
            if arg in inner or "loadFail" in inner:
                out.append(src[start : j + 1])
            else:
                if inner.strip():
                    out.append(f"{fn}({inner}, {arg})")
                else:
                    out.append(f"{fn}({arg})")
            i = j + 1
        return "".join(out)

    body = add_arg_to_calls(body, target_fn, t_expr)
    path.write_text(head + body, encoding="utf-8")
    print("OK", path.name, target_fn, "->", t_expr)


def main() -> None:
    names = [
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
        "keys-panel.tsx",
        "billing-panel.tsx",
        "security-panel.tsx",
    ]
    for name in names:
        process(COMP / name)


if __name__ == "__main__":
    main()
