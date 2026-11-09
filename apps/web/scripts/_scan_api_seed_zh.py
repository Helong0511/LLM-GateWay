# -*- coding: utf-8 -*-
"""Find Chinese in API files that become list labels/notes shown in admin UI."""
from __future__ import annotations

import re
from pathlib import Path

root = Path(__file__).resolve().parents[2] / "api" / "app"
# Focus files that feed list UIs
targets = [
    root / "providers" / "presets.py",
    root / "payments" / "service.py",
    root / "ops" / "service.py",
    root / "admin",
]
zh = re.compile(r"[\u4e00-\u9fff]")
lit = re.compile(r"""["']([^"'\\]{0,200})["']""")

for path in targets:
    files = [path] if path.is_file() else sorted(path.rglob("*.py")) if path.is_dir() else []
    for p in files:
        text = p.read_text(encoding="utf-8")
        hits = []
        for m in lit.finditer(text):
            s = m.group(1)
            if zh.search(s) and not s.startswith("充值订单") and "入账必须" not in s:
                # skip pure docstrings later
                hits.append(s)
        # only report label-like short UI strings
        for s in hits:
            if any(
                k in s
                for k in (
                    "兼容",
                    "可选",
                    "本地",
                    "自建",
                    "通用",
                    "入门",
                    "常用",
                    "更多",
                    "赠送",
                    "优惠券",
                )
            ):
                print(f"{p.relative_to(root)}: {s}")
