"""解密管理端导出的备份文件。

用法：
    BACKUP_ENCRYPTION_KEY=<fernet-key> python scripts/decrypt_backup.py forge-20261109.dump.enc
    BACKUP_ENCRYPTION_KEY=... python scripts/decrypt_backup.py in.dump.enc out.dump

密钥只从环境变量读取，不接受命令行参数：参数会进入 shell 历史与进程列表，
备份密钥泄漏等于全库泄漏。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def main() -> int:
    parser = argparse.ArgumentParser(description="解密 .enc 备份文件")
    parser.add_argument("source", type=Path, help="加密备份路径")
    parser.add_argument("target", type=Path, nargs="?", help="输出路径，默认去掉 .enc 后缀")
    args = parser.parse_args()

    raw_key = os.environ.get("BACKUP_ENCRYPTION_KEY", "")
    if not raw_key:
        print("BACKUP_ENCRYPTION_KEY 未设置", file=sys.stderr)
        return 2
    if not args.source.is_file():
        print(f"文件不存在：{args.source}", file=sys.stderr)
        return 2
    target = args.target or args.source.with_name(args.source.name.removesuffix(".enc"))
    try:
        plaintext = Fernet(raw_key.encode()).decrypt(args.source.read_bytes())
    except (InvalidToken, ValueError):
        print("解密失败：密钥不匹配或文件已损坏", file=sys.stderr)
        return 1
    target.write_bytes(plaintext)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
