from pathlib import Path

codes = {
    "DB_NOT_READY": ("数据库未就绪", "Database is not ready.", "資料庫未就緒"),
    "NOTIFICATION_NOT_FOUND": ("通知不存在", "Notification not found.", "通知不存在"),
    "BALANCE_ALERT_THRESHOLD_INVALID": (
        "预警金额无效，较高线不能低于较低线",
        "Invalid alert thresholds: high must be >= low.",
        "預警金額無效，較高線不能低於較低線",
    ),
}
root = Path(r"e:/ZZZ")
path = root / "apps/api/app/core/errors.py"
text = path.read_text(encoding="utf-8")
end = text.find("\n}\n\n\nclass AppError")
if end < 0:
    end = text.find("\n}\n\nclass AppError")
lines = [f'    "{c}": "{zh}",' for c, (zh, _, _) in codes.items() if f'"{c}":' not in text]
if lines:
    path.write_text(text[:end] + "\n" + "\n".join(lines) + text[end:], encoding="utf-8")
    print("backend", len(lines))
for locale, idx in (("zh-CN", 0), ("en", 1), ("zh-TW", 2)):
    f = root / f"apps/web/src/content/{locale}.ts"
    ft = f.read_text(encoding="utf-8")
    start = ft.find("  errors: {")
    i = ft.find("{", start)
    depth = 0
    end_i = None
    for j in range(i, len(ft)):
        if ft[j] == "{":
            depth += 1
        elif ft[j] == "}":
            depth -= 1
            if depth == 0:
                end_i = j
                break
    chunk = ft[start:end_i]
    extra = []
    for c, vals in codes.items():
        if f"{c}:" in chunk:
            continue
        msg = vals[idx].replace('"', '\\"')
        extra.append(f'    {c}: "{msg}",')
    if extra:
        f.write_text(ft[:end_i] + "\n" + "\n".join(extra) + "\n" + ft[end_i:], encoding="utf-8")
        print(locale, len(extra))
