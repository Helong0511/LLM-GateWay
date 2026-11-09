# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(r"e:/ZZZ/apps/api/app")
HAN = re.compile(r"[\u4e00-\u9fff]")
RAISE = re.compile(r"raise AppError\((.*?)\)(?:\s*from|\s*$)", re.S | re.M)

rows: list[tuple[str, str, str]] = []
for path in ROOT.rglob("*.py"):
    if ".venv" in path.parts:
        continue
    text = path.read_text(encoding="utf-8")
    # line-oriented: raise AppError(...) often one line
    for i, line in enumerate(text.splitlines(), 1):
        if "AppError(" not in line or not HAN.search(line):
            continue
        code_m = re.search(r'AppError\(\s*\d+\s*,\s*"([A-Z0-9_]+)"', line)
        if not code_m:
            code_m = re.search(r"AppError\(\s*\d+\s*,\s*'([A-Z0-9_]+)'", line)
        msg_m = re.search(r',"([^"]*[\u4e00-\u9fff][^"]*)"', line)
        if not msg_m:
            msg_m = re.search(r",\s*f?\"([^\"]*[\u4e00-\u9fff][^\"]*)\"", line)
        code = code_m.group(1) if code_m else "?"
        msg = msg_m.group(1)[:80] if msg_m else line.strip()[:80]
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        rows.append((rel, code, msg))

print("total chinese AppError lines", len(rows))
mods = Counter(r[0].split("/")[0] for r in rows)
print("by module:", mods.most_common())
for domain in ("auth", "payments", "billing", "keys", "ops", "gateway", "providers", "models"):
    items = [r for r in rows if r[0].startswith(domain + "/") or f"/{domain}/" in r[0] or r[0].startswith(domain)]
    # filter by path containing domain
    items = [r for r in rows if domain in r[0]]
    print(f"\n=== {domain} ({len(items)}) ===")
    for rel, code, msg in items[:20]:
        print(f"  {code:28} {msg}")
