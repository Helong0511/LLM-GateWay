# -*- coding: utf-8 -*-
"""Scan API for Chinese literals in fields likely shown in admin UI."""
from __future__ import annotations

import re
from pathlib import Path

root = Path(__file__).resolve().parents[2] / "api" / "app"
pat = re.compile(
    r"""(?:label|note|name|title|reason)\s*=\s*["']([^"']*[\u4e00-\u9fff][^"']*)["']"""
)
str_pat = re.compile(r"""["']([^"']*[\u4e00-\u9fff][^"']{0,120})["']""")

print("=== field assignments ===")
for p in sorted(root.rglob("*.py")):
    text = p.read_text(encoding="utf-8")
    for m in pat.finditer(text):
        print(f"{p.relative_to(root)}: {m.group(0)[:120]}")

print("\n=== seed/product display names etc ===")
for p in [
    root / "providers" / "presets.py",
    root / "payments" / "service.py",
    root / "ops" / "service.py",
]:
    if not p.exists():
        continue
    text = p.read_text(encoding="utf-8")
    for m in str_pat.finditer(text):
        s = m.group(1)
        if any(k in s for k in ("入门", "常用", "兼容", "可选", "本地", "自建", "赠送", "充值")):
            print(f"{p.name}: {s}")
