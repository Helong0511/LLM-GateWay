"""列表分页。默认 20 条，上限 100。排序必须带唯一键，避免同时间戳翻页漏数或重复。"""

from __future__ import annotations


def clamp_page(
    page: int, page_size: int, *, default_size: int = 20, max_size: int = 100
) -> tuple[int, int]:
    safe_page = max(int(page or 1), 1)
    size = int(page_size or default_size)
    safe_size = min(max(size, 1), max_size)
    return safe_page, safe_size


def page_offset(page: int, page_size: int) -> int:
    return (page - 1) * page_size


def page_meta(page: int, page_size: int, total: int) -> dict[str, int]:
    safe_total = max(int(total), 0)
    return {
        "page": page,
        "page_size": page_size,
        "total": safe_total,
        "pages": max(1, (safe_total + page_size - 1) // page_size) if safe_total else 1,
    }
