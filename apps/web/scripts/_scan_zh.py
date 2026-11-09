# -*- coding: utf-8 -*-
import re
from pathlib import Path

comp = Path(__file__).resolve().parents[1] / "src" / "components"
pat = re.compile(r"""["']([^"'\\]*(?:\\.[^"'\\]*)*[\u4e00-\u9fff][^"'\\]*(?:\\.[^"'\\]*)*)["']""")
found: dict[str, list[str]] = {}
for p in sorted(comp.glob("*.tsx")):
    text = p.read_text(encoding="utf-8")
    for m in pat.finditer(text):
        s = m.group(1)
        if len(s) < 2:
            continue
        found.setdefault(s, []).append(p.name)
print(f"Total unique Chinese literals: {len(found)}")
for s, files in sorted(found.items(), key=lambda x: (-len(x[1]), x[0])):
    print(f"{len(files):2d} | {s[:90]} | {','.join(sorted(set(files))[:3])}")
