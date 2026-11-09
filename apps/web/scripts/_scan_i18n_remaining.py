# -*- coding: utf-8 -*-
"""Thorough scan of remaining Chinese UI leaks (frontend literals + API display fields)."""
from __future__ import annotations

import re
from pathlib import Path

web = Path(r"e:\ZZZ\apps\web\src\components")
api = Path(r"e:\ZZZ\apps\api\app")
zh = re.compile(r"[\u4e00-\u9fff]")
# string / template literals with Chinese (skip multi-line junk roughly)
LIT = re.compile(r"""(?P<q>["'`])(?P<body>(?:\\.|(?!(?P=q)).)*?[\u4e00-\u9fff](?:\\.|(?!(?P=q)).)*?)(?P=q)""")
# JSX text nodes with Chinese
JSX = re.compile(r">([^<>{}\n]*[\u4e00-\u9fff][^<>{}\n]*)<")

API_KEY = re.compile(
    r"""["'](status_label|label|title|note|warning|hint|message|reason|balance_note|balance_reason|usable_reason|hint_code)["']\s*:\s*f?(?P<q>["'])(?P<body>(?:\\.|(?!(?P=q)).)*?)(?P=q)"""
)
API_EQ = re.compile(
    r"""\b(title|note|warning|hint|reason)\s*=\s*f?(?P<q>["'])(?P<body>(?:\\.|(?!(?P=q)).)*?[\u4e00-\u9fff](?:\\.|(?!(?P=q)).)*?)(?P=q)"""
)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


print("=" * 60)
print("FRONTEND: Chinese in components (by file)")
print("=" * 60)
file_hits: dict[str, list[tuple[int, str]]] = {}
for p in sorted(web.glob("*.tsx")):
    text = p.read_text(encoding="utf-8")
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        if not zh.search(line):
            continue
        # keep actionable UI-ish lines
        if any(
            k in line
            for k in (
                "setFlash",
                "confirm(",
                "prompt(",
                "placeholder=",
                "hint=",
                "infoFlash",
                "okFlash",
                "warnFlash",
                "errFlash",
                "resultFlash",
                "errorMessage(",
                ">",
                "return ",
                "`",
                '"',
                "'",
            )
        ):
            body = clean(line)
            if len(body) > 8:
                hits.append((i, body[:140]))
    if hits:
        file_hits[p.name] = hits

for name, hits in sorted(file_hits.items(), key=lambda x: -len(x[1])):
    print(f"\n## {name} ({len(hits)})")
    for ln, body in hits[:25]:
        print(f"  L{ln}: {body}")
    if len(hits) > 25:
        print(f"  ... +{len(hits) - 25} more")

print("\n" + "=" * 60)
print("API: Chinese values on UI-ish keys")
print("=" * 60)
for p in sorted(api.rglob("*.py")):
    if ".venv" in str(p):
        continue
    text = p.read_text(encoding="utf-8")
    rel = str(p.relative_to(api))
    for m in API_KEY.finditer(text):
        body = m.group("body")
        if zh.search(body):
            print(f"{rel}: {m.group(1)}={clean(body)[:100]}")
    for m in API_EQ.finditer(text):
        print(f"{rel}: {m.group(1)}={clean(m.group('body'))[:100]}")

print("\nDONE")
