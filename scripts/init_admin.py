"""生成一次性超管初始化令牌。明文只向标准输出打印一次，磁盘只保存 SHA-256。"""

from __future__ import annotations

import hashlib
import secrets
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / ".data" / "admin_init_token.sha256"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        print(
            "初始化令牌摘要已存在。确认无人持有旧明文后，删除 .data/admin_init_token.sha256 再重新生成。",
            file=sys.stderr,
        )
        return 1
    token = "init_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    target.write_text(digest + "\n", encoding="utf-8")
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
