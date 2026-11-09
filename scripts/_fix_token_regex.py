"""把测试里的中文「令牌：」解析改为兼容英文 token:。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tests"
OLD = r'r"令牌：(\S+)"'
NEW = r'r"(?:令牌：|[Tt]oken:\s*)(\S+)"'
OLD2 = r"r'令牌：(\S+)'"
NEW2 = r"r'(?:令牌：|[Tt]oken:\s*)(\S+)'"


def main() -> None:
    updated = 0
    for path in ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        nxt = text.replace(OLD, NEW).replace(OLD2, NEW2)
        if nxt != text:
            path.write_text(nxt, encoding="utf-8")
            updated += 1
            print(path.relative_to(ROOT.parent))
    print(f"updated {updated} files")


if __name__ == "__main__":
    main()
