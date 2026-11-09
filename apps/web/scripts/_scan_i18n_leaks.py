# -*- coding: utf-8 -*-
"""Scan for API Chinese UI labels and frontend display of raw status_label-like fields."""
from __future__ import annotations

import re
from pathlib import Path

api = Path(r"e:\ZZZ\apps\api\app")
web = Path(r"e:\ZZZ\apps\web\src")
zh = re.compile(r"[\u4e00-\u9fff]")

# 1) Backend dict keys that look like UI copy
KEY_ASSIGN = re.compile(
    r"""["'](status_label|label|title|note|message|reason|hint|description|name|warning|body)["']\s*:\s*f?["']([^"']*)["']"""
)
# Also: status_label = "中文"
EQ_ASSIGN = re.compile(
    r"""\b(status_label|label|title|note|reason|warning)\s*=\s*f?["']([^"']*[\u4e00-\u9fff][^"']*)["']"""
)

print("=== API: Chinese values assigned to UI-ish keys ===")
for p in sorted(api.rglob("*.py")):
    if ".venv" in str(p):
        continue
    text = p.read_text(encoding="utf-8")
    rel = p.relative_to(api)
    for m in KEY_ASSIGN.finditer(text):
        key, val = m.group(1), m.group(2)
        if zh.search(val) and len(val) < 120:
            print(f"{rel}: {key}={val}")
    for m in EQ_ASSIGN.finditer(text):
        print(f"{rel}: {m.group(1)}={m.group(2)[:100]}")

print("\n=== Web: rendering item.status_label / raw Chinese fallbacks ===")
pat_render = re.compile(r"status_label|\.note\b|usable_reason")
for p in sorted((web / "components").glob("*.tsx")):
    text = p.read_text(encoding="utf-8")
    if "status_label" in text or re.search(r"text\(item\.(note|reason|title|label|warning)\)", text):
        for i, line in enumerate(text.splitlines(), 1):
            if "status_label" in line or re.search(
                r"text\(item\.(note|reason|title|label|warning|status_label)\)", line
            ):
                print(f"{p.name}:{i}: {line.strip()[:120]}")

print("\n=== Web: hardcoded Chinese string literals in components (sample) ===")
lit = re.compile(r"""["`]([^"`]*[\u4e00-\u9fff][^"`]{0,80})["`]""")
counts: dict[str, int] = {}
for p in sorted((web / "components").glob("*.tsx")):
    text = p.read_text(encoding="utf-8")
    n = 0
    for m in lit.finditer(text):
        s = m.group(1)
        # skip comments-only context roughly
        if s.startswith(" ") and "\n" in s:
            continue
        if len(s) >= 2:
            n += 1
    if n:
        counts[p.name] = n
for name, n in sorted(counts.items(), key=lambda x: -x[1]):
    print(f"{n:3d}  {name}")
