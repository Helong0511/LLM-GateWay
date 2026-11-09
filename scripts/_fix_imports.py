from pathlib import Path

root = Path(r"e:/ZZZ/apps/web/src/components")
for p in root.glob("*.tsx"):
    t = p.read_text(encoding="utf-8")
    n = t.replace(",  ", ", ")
    # drop unused errorMessage import if no call sites
    if "errorMessage(" not in n and "errorMessage" in n:
        n = n.replace(", errorMessage,", ",")
        n = n.replace("errorMessage, ", "")
        n = n.replace(", errorMessage", "")
    if n != t:
        p.write_text(n, encoding="utf-8")
        print("fixed", p.name)
