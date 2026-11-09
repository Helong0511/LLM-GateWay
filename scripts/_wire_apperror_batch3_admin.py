# -*- coding: utf-8 -*-
"""Batch 3: admin + crud_ext stable codes + catalogs."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"e:/ZZZ")

CATALOG: dict[str, tuple[str, str, str]] = {
    "ADMIN_BUDGET_POSITIVE": ("预算必须大于 0", "Budget must be greater than 0.", "預算必須大於 0"),
    "SANCTION_PATCH_EMPTY": ("请至少提供要修改的来源或原因说明", "Provide at least a source or reason to update.", "請至少提供要修改的來源或原因說明"),
    "SANCTION_NETWORK_INVALID": ("网络不支持：请填写支持的链类型", "Unsupported network. Use a supported chain.", "網路不支援：請填寫支援的鏈類型"),
    "SANCTION_ADDRESS_REQUIRED": ("请填写链上地址", "On-chain address is required.", "請填寫鏈上位址"),
    "SANCTION_ADDRESS_TOO_LONG": ("地址过长（最多 {max} 个字符）", "Address too long (max {max} characters).", "位址過長（最多 {max} 個字元）"),
    "SANCTION_ERC20_HEX": ("ERC20 地址须为十六进制（可带 0x 前缀）", "ERC20 address must be hex (optional 0x).", "ERC20 位址須為十六進位（可帶 0x 前綴）"),
    "SANCTION_ERC20_LENGTH": ("ERC20 地址应为 40 位十六进制（不含 0x 时）", "ERC20 address must be 40 hex digits without 0x.", "ERC20 位址應為 40 位十六進位（不含 0x 時）"),
    "SANCTION_TRC20_WHITESPACE": ("TRC20 地址不能包含空白字符", "TRC20 address cannot contain whitespace.", "TRC20 位址不能包含空白字元"),
    "SANCTION_TRC20_PREFIX": ("TRC20 地址通常以 T 开头，请核对是否粘贴完整", "TRC20 address usually starts with T.", "TRC20 位址通常以 T 開頭，請核對是否貼上完整"),
    "SANCTION_TRC20_LENGTH": ("TRC20 地址长度异常，请核对是否粘贴完整", "Unexpected TRC20 address length.", "TRC20 位址長度異常，請核對是否貼上完整"),
    "SANCTION_SOURCE_REQUIRED": ("请填写来源（例如 OFAC SDN、人工录入、网关同步）", "Source is required (e.g. OFAC SDN).", "請填寫來源（例如 OFAC SDN、人工錄入、閘道同步）"),
    "SANCTION_SOURCE_TOO_LONG": ("来源过长（最多 {max} 个字符）", "Source too long (max {max} characters).", "來源過長（最多 {max} 個字元）"),
    "SANCTION_REASON_TOO_LONG": ("原因说明过长（最多 {max} 个字符）", "Reason too long (max {max} characters).", "原因說明過長（最多 {max} 個字元）"),
    "SANCTION_ALREADY_EXISTS": ("该地址已在「{network}」制裁名单中（来源：{source}）。如需改说明请编辑，勿重复添加。", "Address already sanctioned on 「{network}」 (source: {source}).", "該位址已在「{network}」制裁名單中（來源：{source}）。如需改說明請編輯，勿重複新增。"),
    "SANCTION_NOT_FOUND": ("制裁地址不存在（可能已删除）", "Sanctioned address not found (may be deleted).", "制裁位址不存在（可能已刪除）"),
    "SANCTION_SOURCE_EMPTY": ("来源不能为空", "Source cannot be empty.", "來源不能為空"),
    "USER_FILTER_STATUS_INVALID": ("筛选状态不正确，只能是正常或冻结", "Filter status must be active or frozen.", "篩選狀態不正確，只能是正常或凍結"),
    "USER_SEARCH_TOO_LONG": ("搜索关键字过长", "Search keyword is too long.", "搜尋關鍵字過長"),
    "USER_STATUS_INVALID": ("只能改为正常或冻结", "Status can only be active or frozen.", "只能改為正常或凍結"),
    "USER_CANNOT_FREEZE_SELF": ("不能冻结自己的账号", "You cannot freeze your own account.", "不能凍結自己的帳號"),
    "USER_STATUS_TYPE_FORBIDDEN": ("该账号类型不能在此改状态（例如已注销账号）", "This account type cannot change status here.", "該帳號類型不能在此改狀態（例如已註銷帳號）"),
    "USER_CANNOT_DELETE_SELF": ("不能注销自己的账号", "You cannot close your own account.", "不能註銷自己的帳號"),
    "USER_DELETE_TYPE_FORBIDDEN": ("这个账号不能在这里注销", "This account cannot be closed here.", "這個帳號不能在這裡註銷"),
    "KEY_IMMUTABLE_DELETED": ("已删除或已过期的密钥不能修改，请新建密钥", "Deleted/expired keys cannot be edited. Create a new key.", "已刪除或已過期的金鑰不能修改，請新建金鑰"),
    "KEY_STATUS_TOGGLE_FORBIDDEN": ("当前密钥状态不能切换启用/停用", "Cannot toggle enable/disable for this key status.", "目前金鑰狀態不能切換啟用/停用"),
    "KEY_DISABLED_EDIT_FORBIDDEN": ("已停用的密钥请先启用后再修改名称或限额；删除请用删除接口", "Re-enable a disabled key before editing name/limits.", "已停用的金鑰請先啟用後再修改名稱或限額；刪除請用刪除介面"),
    "ALLOWLIST_NOT_FOUND": ("白名单条目不存在", "Allowlist entry not found.", "白名單條目不存在"),
    "PROVIDER_NAME_REQUIRED": ("名称不能为空", "Name cannot be empty.", "名稱不能為空"),
    "PROVIDER_BASE_URL_INVALID": ("基础地址无效：须为完整的 http(s) URL", "Base URL must be a full http(s) URL.", "基礎位址無效：須為完整的 http(s) URL"),
    "PROVIDER_DELETED_IMMUTABLE": ("供应商已删除，不能修改；请先恢复", "Provider is deleted; restore before editing.", "供應商已刪除，不能修改；請先恢復"),
    "CREDENTIAL_NOT_FOUND": ("凭证不存在", "Credential not found.", "憑證不存在"),
    "ROLE_USER_REVOKE_FORBIDDEN": ("不能撤销基础用户角色", "Cannot revoke the base user role.", "不能撤銷基礎使用者角色"),
    "COUPON_DELETED_IMMUTABLE": ("优惠券已删除，不能修改或启用/停用；请先恢复", "Coupon is deleted; restore before editing.", "優惠券已刪除，不能修改或啟用/停用；請先恢復"),
    "COUPON_MAX_USES_INVALID": ("可兑换总次数无效：须为正整数，且不能小于已兑换次数", "Max uses must be a positive integer ≥ used count.", "可兌換總次數無效：須為正整數，且不能小於已兌換次數"),
    "ANNOUNCEMENT_TITLE_EMPTY": ("标题不能为空", "Title cannot be empty.", "標題不能為空"),
    "ANNOUNCEMENT_BODY_EMPTY": ("内容不能为空", "Body cannot be empty.", "內容不能為空"),
    "INVOICE_CANCEL_PENDING_ONLY": ("只能撤销待审核的发票申请", "Only pending invoice requests can be cancelled.", "只能撤銷待審核的發票申請"),
    "PRODUCT_DELETED_IMMUTABLE": ("套餐已删除，不能修改或启用/停用；请先恢复", "Package is deleted; restore before editing.", "套餐已刪除，不能修改或啟用/停用；請先恢復"),
    "LEDGER_ADJUST_DIRECTION": ("方向只能是 C 或 D", "Direction must be C or D.", "方向只能是 C 或 D"),
    "LEDGER_ADJUST_REASON_REQUIRED": ("请填写调账原因", "Adjustment reason is required.", "請填寫調帳原因"),
    "ORDER_CANCEL_PENDING_ONLY": ("只能取消待支付订单", "Only pending orders can be cancelled.", "只能取消待支付訂單"),
    "ORDER_CLOSE_PENDING_ONLY": ("只能关闭待支付订单", "Only pending orders can be closed.", "只能關閉待支付訂單"),
    "PRODUCT_RESTORE_NOT_DELETED": ("套餐未删除，无需恢复；请用启用/停用", "Package is not deleted; use enable/disable.", "套餐未刪除，無需恢復；請用啟用/停用"),
    "COUPON_RESTORE_NOT_DELETED": ("优惠券未删除，无需恢复；请用启用/停用", "Coupon is not deleted; use enable/disable.", "優惠券未刪除，無需恢復；請用啟用/停用"),
    "PROVIDER_RESTORE_NOT_DELETED": ("只有已删除的供应商可以恢复；当前请用启用/停用", "Only deleted providers can be restored.", "只有已刪除的供應商可以恢復；目前請用啟用/停用"),
    "IDEMPOTENCY_KEY_REQUIRED_GENERIC": ("请在请求头提供 Idempotency-Key，避免重复提交", "Provide an Idempotency-Key header.", "請在請求頭提供 Idempotency-Key，避免重複提交"),
}


def inject(catalog: dict[str, tuple[str, str, str]]) -> None:
    path = ROOT / "apps/api/app/core/errors.py"
    text = path.read_text(encoding="utf-8")
    end = text.find("\n}\n\n\nclass AppError")
    if end < 0:
        end = text.find("\n}\n\nclass AppError")
    if end < 0:
        raise SystemExit("MESSAGE_BY_CODE end missing")
    lines = [f'    "{code}": "{zh}",' for code, (zh, _e, _t) in catalog.items() if f'"{code}":' not in text]
    if lines:
        path.write_text(text[:end] + "\n" + "\n".join(lines) + text[end:], encoding="utf-8")
        print(f"backend +{len(lines)}")
    for locale, idx in (("zh-CN", 0), ("en", 1), ("zh-TW", 2)):
        fpath = ROOT / f"apps/web/src/content/{locale}.ts"
        ftext = fpath.read_text(encoding="utf-8")
        start = ftext.find("  errors: {")
        i = ftext.find("{", start)
        depth = 0
        end_i = None
        for j in range(i, len(ftext)):
            if ftext[j] == "{":
                depth += 1
            elif ftext[j] == "}":
                depth -= 1
                if depth == 0:
                    end_i = j
                    break
        assert end_i is not None
        chunk = ftext[start:end_i]
        extra = []
        for code, vals in catalog.items():
            if f"{code}:" in chunk:
                continue
            msg = vals[idx].replace("\\", "\\\\").replace('"', '\\"')
            extra.append(f'    {code}: "{msg}",')
        if extra:
            fpath.write_text(ftext[:end_i] + "\n" + "\n".join(extra) + "\n" + ftext[end_i:], encoding="utf-8")
            print(f"{locale} +{len(extra)}")


def apply_pairs(path: Path, pairs: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old not in text:
            print(f"WARN {path.name}: {old[:70]!r}")
            continue
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print("ok", path.name)


def main() -> None:
    apply_pairs(
        ROOT / "apps/api/app/admin/router.py",
        [
            ('raise AppError(400, "VALIDATION_ERROR", "预算必须大于 0")', 'raise AppError(400, "ADMIN_BUDGET_POSITIVE")'),
            ('raise AppError(400, "VALIDATION_ERROR", "请至少提供要修改的来源或原因说明")', 'raise AppError(400, "SANCTION_PATCH_EMPTY")'),
        ],
    )
    apply_pairs(
        ROOT / "apps/api/app/admin/users.py",
        [
            ('raise AppError(400, "VALIDATION_ERROR", "筛选状态不正确，只能是正常或冻结")', 'raise AppError(400, "USER_FILTER_STATUS_INVALID")'),
            ('raise AppError(400, "VALIDATION_ERROR", "搜索关键字过长")', 'raise AppError(400, "USER_SEARCH_TOO_LONG")'),
            ('raise AppError(400, "VALIDATION_ERROR", "只能改为正常或冻结")', 'raise AppError(400, "USER_STATUS_INVALID")'),
            ('raise AppError(400, "VALIDATION_ERROR", "不能冻结自己的账号")', 'raise AppError(400, "USER_CANNOT_FREEZE_SELF")'),
            ('raise AppError(404, "NOT_FOUND", "用户不存在")', 'raise AppError(404, "USER_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "该账号类型不能在此改状态（例如已注销账号）")', 'raise AppError(400, "USER_STATUS_TYPE_FORBIDDEN")'),
        ],
    )

    crypto = ROOT / "apps/api/app/admin/crypto.py"
    t = crypto.read_text(encoding="utf-8")
    crypto_pairs = [
        ('raise AppError(400, "VALIDATION_ERROR", "请填写链上地址")', 'raise AppError(400, "SANCTION_ADDRESS_REQUIRED")'),
        ('raise AppError(400, "VALIDATION_ERROR", f"地址过长（最多 {ADDRESS_MAX} 个字符）")', 'raise AppError(400, "SANCTION_ADDRESS_TOO_LONG", details={"max": ADDRESS_MAX})'),
        ('raise AppError(400, "VALIDATION_ERROR", "ERC20 地址须为十六进制（可带 0x 前缀）")', 'raise AppError(400, "SANCTION_ERC20_HEX")'),
        ('raise AppError(400, "VALIDATION_ERROR", "ERC20 地址应为 40 位十六进制（不含 0x 时）")', 'raise AppError(400, "SANCTION_ERC20_LENGTH")'),
        ('raise AppError(400, "VALIDATION_ERROR", "TRC20 地址不能包含空白字符")', 'raise AppError(400, "SANCTION_TRC20_WHITESPACE")'),
        ('raise AppError(400, "VALIDATION_ERROR", "TRC20 地址通常以 T 开头，请核对是否粘贴完整")', 'raise AppError(400, "SANCTION_TRC20_PREFIX")'),
        ('raise AppError(400, "VALIDATION_ERROR", "TRC20 地址长度异常，请核对是否粘贴完整")', 'raise AppError(400, "SANCTION_TRC20_LENGTH")'),
        ('raise AppError(400, "VALIDATION_ERROR", "请填写来源（例如 OFAC SDN、人工录入、网关同步）")', 'raise AppError(400, "SANCTION_SOURCE_REQUIRED")'),
        ('raise AppError(400, "VALIDATION_ERROR", f"来源过长（最多 {SOURCE_MAX} 个字符）")', 'raise AppError(400, "SANCTION_SOURCE_TOO_LONG", details={"max": SOURCE_MAX})'),
        ('raise AppError(400, "VALIDATION_ERROR", f"原因说明过长（最多 {REASON_MAX} 个字符）")', 'raise AppError(400, "SANCTION_REASON_TOO_LONG", details={"max": REASON_MAX})'),
        ('raise AppError(404, "NOT_FOUND", "制裁地址不存在（可能已删除）")', 'raise AppError(404, "SANCTION_NOT_FOUND")'),
        ('raise AppError(400, "VALIDATION_ERROR", "来源不能为空")', 'raise AppError(400, "SANCTION_SOURCE_EMPTY")'),
    ]
    for old, new in crypto_pairs:
        if old not in t:
            print("WARN crypto", old[:60])
        t = t.replace(old, new)
    old_net = '''        raise AppError(
            400,
            "VALIDATION_ERROR",
            f"网络不支持：请填写 {' / '.join(sorted(SANCTION_NETWORKS))}（当前仅支持这些链）",
        )'''
    if old_net in t:
        t = t.replace(old_net, '        raise AppError(400, "SANCTION_NETWORK_INVALID")')
        print("crypto network")
    else:
        print("WARN crypto network missing")
    old_dup = '''        raise AppError(
            409,
            "CONFLICT",
            f"该地址已在「{net}」制裁名单中（来源：{existing.source}）。如需改说明请编辑，勿重复添加。",
        )'''
    if old_dup in t:
        t = t.replace(
            old_dup,
            '        raise AppError(409, "SANCTION_ALREADY_EXISTS", details={"network": net, "source": existing.source})',
        )
        print("crypto dup")
    else:
        print("WARN crypto dup missing")
    crypto.write_text(t, encoding="utf-8")

    # crud_ext router — reuse KEY_* codes from earlier batch
    apply_pairs(
        ROOT / "apps/api/app/crud_ext/router.py",
        [
            ('raise AppError(400, "VALIDATION_ERROR", "到期时间格式不正确，请使用带时区的 ISO 时间") from exc', 'raise AppError(400, "KEY_EXPIRES_BAD_FORMAT") from exc'),
            ('raise AppError(400, "VALIDATION_ERROR", "到期时间必须带时区（例如以 Z 或 +08:00 结尾）")', 'raise AppError(400, "KEY_EXPIRES_TZ_REQUIRED")'),
            ('raise AppError(400, "VALIDATION_ERROR", "预算必须是有效的十进制数字") from exc', 'raise AppError(400, "KEY_BUDGET_BAD_FORMAT") from exc'),
            ('raise AppError(400, "VALIDATION_ERROR", "预算必须大于 0")', 'raise AppError(400, "KEY_BUDGET_POSITIVE")'),
            ('raise AppError(400, "VALIDATION_ERROR", "请在请求头提供 Idempotency-Key，避免重复提交")', 'raise AppError(400, "IDEMPOTENCY_KEY_REQUIRED_GENERIC")'),
        ],
    )

    apply_pairs(
        ROOT / "apps/api/app/crud_ext/service.py",
        [
            ('raise AppError(404, "NOT_FOUND", "密钥不存在")', 'raise AppError(404, "KEY_NOT_FOUND")'),
            ('raise AppError(409, "CONFLICT", "已删除或已过期的密钥不能修改，请新建密钥")', 'raise AppError(409, "KEY_IMMUTABLE_DELETED")'),
            ('raise AppError(409, "CONFLICT", "当前密钥状态不能切换启用/停用")', 'raise AppError(409, "KEY_STATUS_TOGGLE_FORBIDDEN")'),
            ('raise AppError(409, "CONFLICT", "已停用的密钥请先启用后再修改名称或限额；删除请用删除接口")', 'raise AppError(409, "KEY_DISABLED_EDIT_FORBIDDEN")'),
            ('raise AppError(400, "VALIDATION_ERROR", "密钥名称需要在 1 到 128 个字符之间")', 'raise AppError(400, "KEY_NAME_INVALID")'),
            ('raise AppError(404, "NOT_FOUND", "白名单条目不存在")', 'raise AppError(404, "ALLOWLIST_NOT_FOUND")'),
            ('raise AppError(404, "NOT_FOUND", "供应商不存在")', 'raise AppError(404, "PROVIDER_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "名称不能为空")', 'raise AppError(400, "PROVIDER_NAME_REQUIRED")'),
            ('raise AppError(400, "VALIDATION_ERROR", "基础地址无效：须为完整的 http(s) URL")', 'raise AppError(400, "PROVIDER_BASE_URL_INVALID")'),
            ('raise AppError(409, "CONFLICT", "供应商已删除，不能修改；请先恢复")', 'raise AppError(409, "PROVIDER_DELETED_IMMUTABLE")'),
            ('raise AppError(404, "NOT_FOUND", "凭证不存在")', 'raise AppError(404, "CREDENTIAL_NOT_FOUND")'),
            ('raise AppError(404, "NOT_FOUND", "模型不存在")', 'raise AppError(404, "PROVIDER_MODEL_NOT_FOUND")'),
            ('raise AppError(403, "FORBIDDEN", "不能通过该接口撤销超级管理员")', 'raise AppError(403, "ROLE_SUPERADMIN_FORBIDDEN")'),
            ('raise AppError(400, "VALIDATION_ERROR", "不能撤销基础用户角色")', 'raise AppError(400, "ROLE_USER_REVOKE_FORBIDDEN")'),
            ('raise AppError(400, "VALIDATION_ERROR", "角色不存在")', 'raise AppError(400, "ROLE_NOT_FOUND")'),
            ('raise AppError(404, "NOT_FOUND", "用户不存在")', 'raise AppError(404, "USER_NOT_FOUND")'),
            ('raise AppError(404, "NOT_FOUND", "优惠券不存在")', 'raise AppError(404, "COUPON_ADMIN_NOT_FOUND")'),
            ('raise AppError(409, "CONFLICT", "优惠券已删除，不能修改或启用/停用；请先恢复")', 'raise AppError(409, "COUPON_DELETED_IMMUTABLE")'),
            ('raise AppError(400, "VALIDATION_ERROR", "可兑换总次数无效：须为正整数，且不能小于已兑换次数")', 'raise AppError(400, "COUPON_MAX_USES_INVALID")'),
            ('raise AppError(404, "NOT_FOUND", "公告不存在")', 'raise AppError(404, "ANNOUNCEMENT_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "标题不能为空")', 'raise AppError(400, "ANNOUNCEMENT_TITLE_EMPTY")'),
            ('raise AppError(400, "VALIDATION_ERROR", "内容不能为空")', 'raise AppError(400, "ANNOUNCEMENT_BODY_EMPTY")'),
            ('raise AppError(404, "NOT_FOUND", "工单不存在")', 'raise AppError(404, "TICKET_NOT_FOUND")'),
            ('raise AppError(404, "NOT_FOUND", "发票申请不存在")', 'raise AppError(404, "INVOICE_NOT_FOUND")'),
            ('raise AppError(409, "CONFLICT", "只能撤销待审核的发票申请")', 'raise AppError(409, "INVOICE_CANCEL_PENDING_ONLY")'),
            ('raise AppError(400, "VALIDATION_ERROR", "金额必须大于 0")', 'raise AppError(400, "AMOUNT_POSITIVE")'),
            ('raise AppError(404, "NOT_FOUND", "充值套餐不存在")', 'raise AppError(404, "PRODUCT_NOT_FOUND")'),
            ('raise AppError(409, "CONFLICT", "套餐已删除，不能修改或启用/停用；请先恢复")', 'raise AppError(409, "PRODUCT_DELETED_IMMUTABLE")'),
            ('raise AppError(400, "VALIDATION_ERROR", "方向只能是 C 或 D")', 'raise AppError(400, "LEDGER_ADJUST_DIRECTION")'),
            ('raise AppError(400, "VALIDATION_ERROR", "请填写调账原因")', 'raise AppError(400, "LEDGER_ADJUST_REASON_REQUIRED")'),
            ('raise AppError(404, "NOT_FOUND", "订单不存在")', 'raise AppError(404, "ORDER_NOT_FOUND")'),
            ('raise AppError(409, "CONFLICT", "只能取消待支付订单")', 'raise AppError(409, "ORDER_CANCEL_PENDING_ONLY")'),
            ('raise AppError(409, "CONFLICT", "只能关闭待支付订单")', 'raise AppError(409, "ORDER_CLOSE_PENDING_ONLY")'),
            ('raise AppError(409, "CONFLICT", "套餐未删除，无需恢复；请用启用/停用")', 'raise AppError(409, "PRODUCT_RESTORE_NOT_DELETED")'),
            ('raise AppError(409, "CONFLICT", "优惠券未删除，无需恢复；请用启用/停用")', 'raise AppError(409, "COUPON_RESTORE_NOT_DELETED")'),
            ('raise AppError(409, "CONFLICT", "只有已删除的供应商可以恢复；当前请用启用/停用")', 'raise AppError(409, "PROVIDER_RESTORE_NOT_DELETED")'),
            ('raise AppError(400, "VALIDATION_ERROR", "不能注销自己的账号")', 'raise AppError(400, "USER_CANNOT_DELETE_SELF")'),
            ('raise AppError(400, "VALIDATION_ERROR", "这个账号不能在这里注销")', 'raise AppError(400, "USER_DELETE_TYPE_FORBIDDEN")'),
        ],
    )

    # remaining multiline in crud_ext if any
    svc = ROOT / "apps/api/app/crud_ext/service.py"
    st = svc.read_text(encoding="utf-8")
    if "raise AppError(" in st and any("\u4e00" <= c <= "\u9fff" for c in st):
        import re
        for i, line in enumerate(st.splitlines(), 1):
            if "AppError" in line and re.search(r"[\u4e00-\u9fff]", line):
                print("REMAIN crud", i, line.strip()[:100])

    inject(CATALOG)
    print("done")


if __name__ == "__main__":
    main()
