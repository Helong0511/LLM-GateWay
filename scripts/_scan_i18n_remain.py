# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from pathlib import Path

HAN = re.compile(r"[\u4e00-\u9fff]")
ROOT = Path(r"e:/ZZZ")


def scan(root: Path, globs: list[str], skip_parts: set[str]) -> None:
    hits: list[tuple[str, int, str]] = []
    for pattern in globs:
        for path in root.rglob(pattern):
            if any(p in path.parts for p in skip_parts):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if not s or s.startswith("//") or s.startswith("#") or s.startswith("*"):
                    continue
                if not HAN.search(line):
                    continue
                hits.append((str(path.relative_to(ROOT)).replace("\\", "/"), i, s[:140]))
    print(f"total {len(hits)}")
    by = {}
    for rel, _, _ in hits:
        top = "/".join(rel.split("/")[:3])
        by[top] = by.get(top, 0) + 1
    for k, v in sorted(by.items(), key=lambda x: -x[1])[:25]:
        print(f"  {v:4} {k}")
    print("--- samples ---")
    for item in hits[:40]:
        print(f"{item[0]}:{item[1]}: {item[2]}")


print("=== API app ===")
scan(
    ROOT / "apps/api/app",
    ["*.py"],
    {".venv", "__pycache__"},
)
print("\n=== Web src (excl content) ===")
scan(
    ROOT / "apps/web/src",
    ["*.ts", "*.tsx"],
    {"content", "node_modules"},
)
