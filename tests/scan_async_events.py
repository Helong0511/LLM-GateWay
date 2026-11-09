"""扫描前端：await 之后仍访问 event.currentTarget / event.target。

用法：
  python tests/scan_async_events.py
退出码 1 表示仍有 BUG（confirm 后读 currentTarget 仅 WARN，不失败）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"

YIELD = re.compile(r"\b(?:await|yield)\b|\bwindow\.confirm\s*\(|\bconfirm\s*\(")


def function_body(text: str, start: int) -> str | None:
    depth = 0
    for index, char in enumerate(text[start:], start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def handlers_in(text: str) -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    patterns = [
        r"async\s+function\s+(\w+)\s*\([^)]*\b(?:event|e)\b[^)]*\)[^{]*\{",
        r"(?:const|let|var)\s+(\w+)\s*=\s*async\s*\([^)]*\b(?:event|e)\b[^)]*\)\s*(?::\s*[^=]+?)?\s*=>\s*\{",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            body = function_body(text, match.end() - 1)
            if body:
                found.append((match.group(1), match.end() - 1, body))
    for match in re.finditer(r"on\w+\s*=\s*\{\s*async\s*\(\s*(?:event|e)\b[^)]*\)\s*=>\s*\{", text):
        body = function_body(text, match.end() - 1)
        if body:
            found.append(("(inline)", match.end() - 1, body))
    return found


def scan_handler(rel: Path, name: str, body: str, text: str, body_start: int) -> tuple[list[str], list[str]]:
    bugs: list[str] = []
    warns: list[str] = []
    for yield_match in YIELD.finditer(body):
        after = body[yield_match.end() :]
        yield_kind = yield_match.group(0)
        abs_line = line_of(text, body_start + yield_match.start())
        for bad in re.finditer(r"\b(?:event|e)\.currentTarget\b|\b(?:event|e)\.target\b", after):
            snippet = after[bad.start() : bad.start() + 48].replace("\n", " ")
            msg = f"{rel}::{name}:{abs_line} 在 `{yield_kind}` 之后仍访问 `{snippet}`"
            if yield_kind.startswith("await") or yield_kind == "yield":
                bugs.append(msg)
            else:
                warns.append(msg + "（confirm 同步通常仍可用，建议先保存 form）")
    return bugs, warns


def collect() -> tuple[list[str], list[str]]:
    bugs: list[str] = []
    warns: list[str] = []
    for path in sorted(list(ROOT.rglob("*.tsx")) + list(ROOT.rglob("*.ts"))):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT.parent.parent.parent)
        for name, body_start, body in handlers_in(text):
            b, w = scan_handler(rel, name, body, text, body_start)
            bugs.extend(b)
            warns.extend(w)
    return bugs, warns


def main() -> int:
    bugs, warns = collect()
    for item in bugs:
        print("BUG", item)
    for item in warns:
        print("WARN", item)
    print(f"bugs={len(bugs)} warns={len(warns)}")
    return 1 if bugs else 0


if __name__ == "__main__":
    sys.exit(main())
