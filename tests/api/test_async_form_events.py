"""回归：async 表单处理里不得在 await 之后再读 event.currentTarget。"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_scanner():
    path = Path(__file__).resolve().parents[1] / "scan_async_events.py"
    spec = importlib.util.spec_from_file_location("scan_async_events", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_await_after_current_target() -> None:
    scanner = _load_scanner()
    bugs, _warns = scanner.collect()
    assert bugs == [], "\n".join(bugs)
