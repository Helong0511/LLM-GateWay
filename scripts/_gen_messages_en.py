"""从 web en.ts errors 生成 API MESSAGE_BY_CODE_EN。"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EN_TS = ROOT / "apps/web/src/content/en.ts"
OUT = ROOT / "apps/api/app/core/messages_en.py"


def main() -> None:
    text = EN_TS.read_text(encoding="utf-8")
    match = re.search(r"errors:\s*\{([\s\S]*?)\n  \},", text)
    if match is None:
        raise SystemExit("errors block not found in en.ts")
    block = match.group(1)
    pairs = re.findall(r'^\s+([A-Z][A-Z0-9_]+):\s*"((?:\\.|[^"\\])*)"', block, re.M)
    # Also allow template-ish strings without braces issues — skip multiline
    lines = [
        "# 由 scripts/_gen_messages_en.py 从 apps/web/src/content/en.ts 生成；勿手改。",
        "from __future__ import annotations",
        "",
        "MESSAGE_BY_CODE_EN: dict[str, str] = {",
    ]
    for key, value in pairs:
        decoded = ast.literal_eval(f'"{value}"')
        lines.append(f"    {key!r}: {decoded!r},")
    lines.append("}")
    lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({len(pairs)} keys)")


if __name__ == "__main__":
    main()
