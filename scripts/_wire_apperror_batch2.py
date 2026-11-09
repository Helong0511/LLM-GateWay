# -*- coding: utf-8 -*-
"""Batch 2: ops / gateway / providers / billing / security AppError codes + catalogs."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"e:/ZZZ")

# code -> (zh-CN, en, zh-TW)
CATALOG: dict[str, tuple[str, str, str]] = {
    # ops tickets / invoices / announcements / coupons admin
    "TICKET_CATEGORY_INVALID": ("工单分类不支持，请选择列表中的分类", "Unsupported ticket category.", "工單分類不支援，請選擇列表中的分類"),
    "TICKET_EMPTY": ("工单标题和内容不能为空", "Ticket subject and body cannot be empty.", "工單標題與內容不能為空"),
    "TICKET_REPLY_EMPTY": ("回复不能为空", "Reply cannot be empty.", "回覆不能為空"),
    "TICKET_STATUS_INVALID": ("工单状态不支持，请选择列表中的状态", "Unsupported ticket status.", "工單狀態不支援，請選擇列表中的狀態"),
    "TICKET_CLOSED": ("已关闭的工单不能再回复", "Closed tickets cannot be replied to.", "已關閉的工單不能再回覆"),
    "TICKET_NOT_FOUND": ("工单不存在", "Ticket not found.", "工單不存在"),
    "INVOICE_ORDER_NOT_FOUND": ("可开票的订单不存在（须为已支付订单）", "No billable order found (must be a paid order).", "可開票的訂單不存在（須為已支付訂單）"),
    "INVOICE_TITLE_EMPTY": ("发票抬头不能为空", "Invoice title cannot be empty.", "發票抬頭不能為空"),
    "INVOICE_ALREADY_REQUESTED": ("该订单已申请过发票", "An invoice was already requested for this order.", "該訂單已申請過發票"),
    "INVOICE_STATUS_INVALID": ("发票状态不支持，请选择待开票、已开票或已拒绝", "Unsupported invoice status.", "發票狀態不支援，請選擇待開票、已開票或已拒絕"),
    "INVOICE_NOT_FOUND": ("发票申请不存在", "Invoice request not found.", "發票申請不存在"),
    "INVOICE_ALREADY_REVIEWED": ("这张发票已经处理过，不能重复审核", "This invoice was already reviewed.", "這張發票已經處理過，不能重複審核"),
    "ANNOUNCEMENT_EMPTY": ("公告标题和正文不能为空", "Announcement title and body cannot be empty.", "公告標題與正文不能為空"),
    "ANNOUNCEMENT_SLUG_TAKEN": ("公告地址已被使用", "Announcement slug is already in use.", "公告位址已被使用"),
    "ANNOUNCEMENT_NOT_FOUND": ("公告不存在", "Announcement not found.", "公告不存在"),
    "ANNOUNCEMENT_SLUG_INVALID": ("公告地址只能用小写字母、数字和连字符", "Slug may only use lowercase letters, digits, and hyphens.", "公告位址只能用小寫字母、數字與連字號"),
    "COUPON_BONUS_POSITIVE": ("赠送金额必须大于 0", "Bonus amount must be greater than 0.", "贈送金額必須大於 0"),
    "COUPON_MAX_USES_MIN": ("可用次数至少为 1", "Max uses must be at least 1.", "可用次數至少為 1"),
    "COUPON_CODE_EXISTS": ("该优惠券码已存在，请换一个或使用自动生成", "Coupon code already exists. Use another or auto-generate.", "該優惠券碼已存在，請換一個或使用自動產生"),
    "COUPON_ADMIN_NOT_FOUND": ("优惠券不存在", "Coupon not found.", "優惠券不存在"),
    "COUPON_GENERATE_CONFLICT": ("券码生成遇到冲突，请再点一次自动生成；若持续出现请稍后再试", "Code generation conflict. Generate again, or try later.", "券碼產生遇到衝突，請再點一次自動產生；若持續出現請稍後再試"),
    "STATUS_FILTER_INVALID": ("状态筛选只能是 active / disabled / all", "Status filter must be active, disabled, or all.", "狀態篩選只能是 active / disabled / all"),
    "BACKUP_NOT_POSTGRES": ("当前 DATABASE_URL 不是 PostgreSQL，无法备份。请改用 PostgreSQL 或安装 pg_dump。", "DATABASE_URL is not PostgreSQL; backup unavailable.", "目前 DATABASE_URL 不是 PostgreSQL，無法備份。"),
    "BACKUP_DB_URL_INCOMPLETE": ("数据库地址无法用于备份：缺少库名或用户名", "Database URL incomplete for backup (missing db or user).", "資料庫位址無法用於備份：缺少庫名或使用者名稱"),
    "BACKUP_TOOL_MISSING": ("找不到备份程序，请检查 PG_DUMP_PATH 或 Docker", "Backup tool not found. Check PG_DUMP_PATH or Docker.", "找不到備份程式，請檢查 PG_DUMP_PATH 或 Docker"),
    "BACKUP_TIMEOUT": ("备份超时（超过 180 秒），请检查数据库负载后重试", "Backup timed out (>180s). Check DB load and retry.", "備份逾時（超過 180 秒），請檢查資料庫負載後重試"),
    "BACKUP_FAILED": ("备份未完成：{tip}。请核对数据库是否可达、账号是否有导出权限", "Backup failed: {tip}. Check DB reachability and privileges.", "備份未完成：{tip}。請核對資料庫是否可達、帳號是否有匯出權限"),
    "BACKUP_DOCKER_MISSING": ("本机没有 Docker，无法回退备份", "Docker is not available for backup fallback.", "本機沒有 Docker，無法回退備份"),
    "BACKUP_SQL_CONNECT_FAILED": ("无法连接数据库做 SQL 备份：{error}。请确认 PostgreSQL 已启动且 DATABASE_URL 正确", "Cannot connect for SQL backup: {error}.", "無法連線資料庫做 SQL 備份：{error}。"),
    "BACKUP_SQL_FAILED": ("SQL 备份未完成：{error}。请检查账号是否有读表权限", "SQL backup failed: {error}. Check read privileges.", "SQL 備份未完成：{error}。請檢查帳號是否有讀表權限"),
    "BACKUP_EMPTY_FILE": ("备份文件未生成或大小为 0，请检查权限与磁盘空间", "Backup file missing or empty. Check permissions and disk.", "備份檔未產生或大小為 0，請檢查權限與磁碟空間"),
    "BACKUP_NAME_INVALID": ("备份文件名不合法（仅允许 .dump / .sql）", "Invalid backup filename (.dump / .sql only).", "備份檔名不合法（僅允許 .dump / .sql）"),
    "BACKUP_FILE_NOT_FOUND": ("备份文件不存在", "Backup file not found.", "備份檔不存在"),
    # gateway
    "GATEWAY_DB_NOT_READY": ("数据库未就绪", "Database is not ready.", "資料庫未就緒"),
    "GATEWAY_MODEL_REQUIRED": ("必须提供模型名称", "Model name is required.", "必須提供模型名稱"),
    "GATEWAY_KEY_USER_MISSING": ("密钥所属账号不存在", "Account for this API key does not exist.", "金鑰所屬帳號不存在"),
    "GATEWAY_ACCOUNT_UNAVAILABLE": ("账号已冻结或不可用，暂时不能调用", "Account is frozen or unavailable.", "帳號已凍結或不可用，暫時不能呼叫"),
    "GATEWAY_EMBEDDINGS_UNSUPPORTED": ("该模型未确认支持 embeddings，请换用支持向量的模型", "Model does not confirm embeddings support.", "該模型未確認支援 embeddings，請換用支援向量的模型"),
    "GATEWAY_RPM_LIMIT": ("请求过于频繁（已达每分钟次数上限），请稍后再试", "Rate limited (requests per minute).", "請求過於頻繁（已達每分鐘次數上限），請稍後再試"),
    "GATEWAY_TPM_LIMIT": ("请求过于频繁（已达每分钟 Token 上限），请稍后再试", "Rate limited (tokens per minute).", "請求過於頻繁（已達每分鐘 Token 上限），請稍後再試"),
    "GATEWAY_CONCURRENCY_LIMIT": ("当前并发已满，请等待进行中的请求结束后再试", "Concurrency limit reached. Wait and retry.", "目前併發已滿，請等待進行中的請求結束後再試"),
    "GATEWAY_UPSTREAM_STATUS": ("上游返回了错误状态，请稍后再试；若持续出现请联系客服", "Upstream returned an error status. Try again later.", "上游回傳了錯誤狀態，請稍後再試；若持續出現請聯絡客服"),
    "GATEWAY_UPSTREAM_UNREADABLE": ("上游响应暂时无法读取，请稍后再试", "Upstream response could not be read. Try again later.", "上游回應暫時無法讀取，請稍後再試"),
    "GATEWAY_MODEL_NOT_FOUND": ("模型不存在", "Model not found.", "模型不存在"),
    "GATEWAY_MODEL_UNPUBLISHED": ("模型尚未上架，暂时不能调用", "Model is not published yet.", "模型尚未上架，暫時不能呼叫"),
    "GATEWAY_DEPLOYMENT_DISABLED": ("模型部署已停用，暂时不能调用", "Model deployment is disabled.", "模型部署已停用，暫時不能呼叫"),
    "GATEWAY_UPSTREAM_UNREACHABLE": ("暂时连不上模型服务，请稍后再试；若持续出现请联系客服", "Cannot reach the model service. Try again later.", "暫時連不上模型服務，請稍後再試；若持續出現請聯絡客服"),
    "ENDPOINT_NOT_OPEN": ("该接口尚未开放", "This endpoint is not available yet.", "該介面尚未開放"),
    "BODY_MUST_BE_JSON": ("请求体必须是 JSON", "Request body must be JSON.", "請求體必須是 JSON"),
    "BODY_MUST_BE_JSON_OBJECT": ("请求体必须是 JSON 对象", "Request body must be a JSON object.", "請求體必須是 JSON 物件"),
    # providers
    "PROVIDER_TYPE_INVALID": ("供应商类型不支持，请选择列表中的类型", "Unsupported provider type.", "供應商類型不支援，請選擇列表中的類型"),
    "PROVIDER_NAME_EMPTY": ("供应商名称不能为空", "Provider name cannot be empty.", "供應商名稱不能為空"),
    "PROVIDER_CREDENTIAL_EMPTY": ("上游凭证不能为空", "Upstream credential cannot be empty.", "上游憑證不能為空"),
    "PROVIDER_ALLOWLIST_HOST_INVALID": ("白名单主机名格式不正确", "Allowlist hostname format is invalid.", "白名單主機名格式不正確"),
    "PROVIDER_MODEL_NOT_FOUND": ("模型不存在", "Model not found.", "模型不存在"),
    "DEPLOYMENT_STATUS_INVALID": ("部署状态只能是 active（启用）或 disabled（停用）", "Deployment status must be active or disabled.", "部署狀態只能是 active（啟用）或 disabled（停用）"),
    "DEPLOYMENT_NOT_FOUND": ("部署不存在", "Deployment not found.", "部署不存在"),
    "PROVIDER_TEST_TYPE_INVALID": ("测试类型不支持，请选择列表中的类型", "Unsupported test type.", "測試類型不支援，請選擇列表中的類型"),
    "PROVIDER_UPSTREAM_NO_RESPONSE": ("上游没有返回可用响应，请稍后再试或检查凭证与地址", "Upstream returned no usable response.", "上游沒有回傳可用回應，請稍後再試或檢查憑證與位址"),
    "PROVIDER_MODELS_FETCH_FAILED": ("未能读取上游模型清单，请稍后再试或检查连通性", "Could not fetch upstream model list.", "未能讀取上游模型清單，請稍後再試或檢查連通性"),
    "PROVIDER_MODELS_FORMAT_INVALID": ("上游返回的模型清单格式无法识别，请核对供应商类型与地址", "Upstream model list format is unrecognized.", "上游回傳的模型清單格式無法識別，請核對供應商類型與位址"),
    "PROVIDER_NO_CREDENTIAL": ("该供应商还没有可用凭证，请先保存上游密钥", "Provider has no credential yet. Save an upstream key first.", "該供應商還沒有可用憑證，請先儲存上游金鑰"),
    "PROVIDER_NOT_FOUND": ("供应商不存在", "Provider not found.", "供應商不存在"),
    # billing
    "LEDGER_ENTRY_TYPE_INVALID": ("流水类型「{entry_type}」不支持", "Unsupported ledger entry type 「{entry_type}」.", "流水類型「{entry_type}」不支援"),
    "LEDGER_DIRECTION_INVALID": ("流水方向只能是 C（入账）、D（出账）或 N", "Ledger direction must be C, D, or N.", "流水方向只能是 C（入帳）、D（出帳）或 N"),
    "AMOUNT_POSITIVE": ("金额必须大于 0", "Amount must be greater than 0.", "金額必須大於 0"),
    "BALANCE_INSUFFICIENT": ("可用余额不足，无法完成本次入账或扣减", "Insufficient available balance.", "可用餘額不足，無法完成本次入帳或扣減"),
    "HOLD_AMOUNT_POSITIVE": ("预扣金额必须大于 0", "Hold amount must be greater than 0.", "預扣金額必須大於 0"),
    "HOLD_TTL_POSITIVE": ("预扣有效期必须大于 0 秒", "Hold TTL must be greater than 0 seconds.", "預扣有效期必須大於 0 秒"),
    "SETTLE_AMOUNT_NEGATIVE": ("结算金额不能为负数", "Settlement amount cannot be negative.", "結算金額不能為負數"),
    "AMOUNT_BAD_FORMAT": ("金额格式不正确，请输入有效数字", "Invalid amount format.", "金額格式不正確，請輸入有效數字"),
    "AMOUNT_NEGATIVE": ("金额不能为负数", "Amount cannot be negative.", "金額不能為負數"),
    "AMOUNT_SCALE": ("金额最多支持 8 位小数", "Amount supports at most 8 decimal places.", "金額最多支援 8 位小數"),
    "CURRENCY_INVALID": ("币种代码不正确（例如 USD、CNY）", "Invalid currency code (e.g. USD, CNY).", "幣種代碼不正確（例如 USD、CNY）"),
    "BILLING_MODEL_NOT_FOUND": ("模型不存在", "Model not found.", "模型不存在"),
    "PRICE_ITEMS_REQUIRED": ("至少需要一条单价", "At least one price item is required.", "至少需要一條單價"),
    "PRICE_METER_INVALID": ("计量项「{meter}」无效", "Invalid meter 「{meter}」.", "計量項「{meter}」無效"),
    "PRICE_METER_DUPLICATE": ("计量项「{meter}」重复，每条只能出现一次", "Duplicate meter 「{meter}」.", "計量項「{meter}」重複，每條只能出現一次"),
    "PRICE_MIN_UNIT_NEGATIVE": ("最低计费单位不能为负数", "Minimum billable unit cannot be negative.", "最低計費單位不能為負數"),
    "PRICE_VERSION_NOT_FOUND": ("价格版本不存在", "Price version not found.", "價格版本不存在"),
    "PRICE_UNIT_BAD_FORMAT": ("单价格式不正确，请输入有效的十进制数字", "Invalid unit price format.", "單價格式不正確，請輸入有效的十進位數字"),
    "PRICE_MIN_UNIT_INT": ("最低计费单位必须是非负整数", "Minimum unit must be a non-negative integer.", "最低計費單位必須是非負整數"),
    "KEY_BUDGET_EXHAUSTED": ("密钥预算已用完", "Key budget is exhausted.", "金鑰預算已用完"),
    "BILLING_USAGE_NOT_FOUND": ("调用记录不存在", "Usage record not found.", "呼叫記錄不存在"),
    # security / ssrf
    "URL_DNS_FAILED": ("域名无法解析", "Hostname could not be resolved.", "網域無法解析"),
    "URL_SCHEME_INVALID": ("地址只允许 http 或 https，且不能带账号", "URL must be http/https without credentials.", "位址只允許 http 或 https，且不能帶帳號"),
    "URL_HOST_INVALID": ("地址主机名无效", "Invalid URL hostname.", "位址主機名無效"),
    "URL_METADATA_BLOCKED": ("云元数据地址被拒绝", "Cloud metadata address is blocked.", "雲中繼資料位址被拒絕"),
    "URL_ALLOWLIST_REQUIRED": ("自建端点必须先通过白名单", "Self-hosted endpoints must be allowlisted first.", "自建端點必須先通過白名單"),
    "URL_PRIVATE_BLOCKED": ("地址落在私有或保留网段", "Address is in a private or reserved range.", "位址落在私有或保留網段"),
    "URL_REDIRECT_LIMIT": ("重定向次数过多", "Too many redirects.", "重新導向次數過多"),
}

REPLACEMENTS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "apps/api/app/ops/service.py",
        [
            ('raise AppError(400, "VALIDATION_ERROR", "工单分类不支持，请选择列表中的分类")', 'raise AppError(400, "TICKET_CATEGORY_INVALID")'),
            ('raise AppError(400, "VALIDATION_ERROR", "工单标题和内容不能为空")', 'raise AppError(400, "TICKET_EMPTY")'),
            ('raise AppError(400, "VALIDATION_ERROR", "回复不能为空")', 'raise AppError(400, "TICKET_REPLY_EMPTY")'),
            ('raise AppError(400, "VALIDATION_ERROR", "工单状态不支持，请选择列表中的状态")', 'raise AppError(400, "TICKET_STATUS_INVALID")'),
            ('raise AppError(400, "VALIDATION_ERROR", "已关闭的工单不能再回复")', 'raise AppError(400, "TICKET_CLOSED")'),
            ('raise AppError(404, "NOT_FOUND", "可开票的订单不存在（须为已支付订单）")', 'raise AppError(404, "INVOICE_ORDER_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "发票抬头不能为空")', 'raise AppError(400, "INVOICE_TITLE_EMPTY")'),
            ('raise AppError(409, "IDEMPOTENCY_CONFLICT", "该订单已申请过发票") from exc', 'raise AppError(409, "INVOICE_ALREADY_REQUESTED") from exc'),
            ('raise AppError(400, "VALIDATION_ERROR", "发票状态不支持，请选择待开票、已开票或已拒绝")', 'raise AppError(400, "INVOICE_STATUS_INVALID")'),
            ('raise AppError(404, "NOT_FOUND", "发票申请不存在")', 'raise AppError(404, "INVOICE_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "这张发票已经处理过，不能重复审核")', 'raise AppError(400, "INVOICE_ALREADY_REVIEWED")'),
            ('raise AppError(400, "VALIDATION_ERROR", "公告标题和正文不能为空")', 'raise AppError(400, "ANNOUNCEMENT_EMPTY")'),
            ('raise AppError(409, "IDEMPOTENCY_CONFLICT", "公告地址已被使用") from exc', 'raise AppError(409, "ANNOUNCEMENT_SLUG_TAKEN") from exc'),
            ('raise AppError(404, "NOT_FOUND", "公告不存在")', 'raise AppError(404, "ANNOUNCEMENT_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "赠送金额必须大于 0")', 'raise AppError(400, "COUPON_BONUS_POSITIVE")'),
            ('raise AppError(400, "VALIDATION_ERROR", "可用次数至少为 1")', 'raise AppError(400, "COUPON_MAX_USES_MIN")'),
            ('raise AppError(400, "VALIDATION_ERROR", f"券码格式不正确：{exc}") from exc', 'raise AppError(400, "COUPON_BAD_FORMAT", details={"reason": str(exc)}) from exc'),
            ('raise AppError(409, "IDEMPOTENCY_CONFLICT", "该优惠券码已存在，请换一个或使用自动生成")', 'raise AppError(409, "COUPON_CODE_EXISTS")'),
            ('raise AppError(409, "IDEMPOTENCY_CONFLICT", "该优惠券码已存在，请换一个或使用自动生成") from exc', 'raise AppError(409, "COUPON_CODE_EXISTS") from exc'),
            ('raise AppError(404, "NOT_FOUND", "优惠券不存在")', 'raise AppError(404, "COUPON_ADMIN_NOT_FOUND")'),
            ('raise AppError(404, "NOT_FOUND", "工单不存在")', 'raise AppError(404, "TICKET_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "公告地址只能用小写字母、数字和连字符")', 'raise AppError(400, "ANNOUNCEMENT_SLUG_INVALID")'),
        ],
    ),
    (
        "apps/api/app/ops/platform.py",
        [
            ('raise AppError(400, "VALIDATION_ERROR", "状态筛选只能是 active / disabled / all")', 'raise AppError(400, "STATUS_FILTER_INVALID")'),
            ('raise AppError(503, "DEPENDENCY_UNAVAILABLE", "数据库地址无法用于备份：缺少库名或用户名")', 'raise AppError(503, "BACKUP_DB_URL_INCOMPLETE")'),
            ('raise AppError(503, "DEPENDENCY_UNAVAILABLE", "找不到备份程序，请检查 PG_DUMP_PATH 或 Docker") from exc', 'raise AppError(503, "BACKUP_TOOL_MISSING") from exc'),
            ('raise AppError(503, "DEPENDENCY_UNAVAILABLE", "备份超时（超过 180 秒），请检查数据库负载后重试") from exc', 'raise AppError(503, "BACKUP_TIMEOUT") from exc'),
            ('raise AppError(503, "DEPENDENCY_UNAVAILABLE", "本机没有 Docker，无法回退备份")', 'raise AppError(503, "BACKUP_DOCKER_MISSING")'),
            ('raise AppError(503, "DEPENDENCY_UNAVAILABLE", "备份文件未生成或大小为 0，请检查权限与磁盘空间")', 'raise AppError(503, "BACKUP_EMPTY_FILE")'),
            ('raise AppError(400, "VALIDATION_ERROR", "备份文件名不合法（仅允许 .dump / .sql）")', 'raise AppError(400, "BACKUP_NAME_INVALID")'),
            ('raise AppError(404, "NOT_FOUND", "备份文件不存在")', 'raise AppError(404, "BACKUP_FILE_NOT_FOUND")'),
        ],
    ),
    (
        "apps/api/app/gateway/service.py",
        [
            ('raise AppError(400, "VALIDATION_ERROR", "必须提供模型名称")', 'raise AppError(400, "GATEWAY_MODEL_REQUIRED")'),
            ('raise AppError(403, "FORBIDDEN", "密钥所属账号不存在")', 'raise AppError(403, "GATEWAY_KEY_USER_MISSING")'),
            ('raise AppError(403, "FORBIDDEN", "账号已冻结或不可用，暂时不能调用")', 'raise AppError(403, "GATEWAY_ACCOUNT_UNAVAILABLE")'),
            ('raise AppError(404, "NOT_FOUND", "该模型未确认支持 embeddings，请换用支持向量的模型")', 'raise AppError(404, "GATEWAY_EMBEDDINGS_UNSUPPORTED")'),
            ('raise AppError(429, "RATE_LIMITED", "请求过于频繁（已达每分钟次数上限），请稍后再试")', 'raise AppError(429, "GATEWAY_RPM_LIMIT")'),
            ('raise AppError(429, "RATE_LIMITED", "请求过于频繁（已达每分钟 Token 上限），请稍后再试")', 'raise AppError(429, "GATEWAY_TPM_LIMIT")'),
            ('raise AppError(429, "CONCURRENCY_LIMITED", "当前并发已满，请等待进行中的请求结束后再试")', 'raise AppError(429, "GATEWAY_CONCURRENCY_LIMIT")'),
            ('raise AppError(502, "UPSTREAM_ERROR", "上游响应暂时无法读取，请稍后再试") from None', 'raise AppError(502, "GATEWAY_UPSTREAM_UNREADABLE") from None'),
            ('raise AppError(502, "UPSTREAM_ERROR", "上游响应暂时无法读取，请稍后再试")', 'raise AppError(502, "GATEWAY_UPSTREAM_UNREADABLE")'),
            ('raise AppError(404, "NOT_FOUND", "模型不存在")', 'raise AppError(404, "GATEWAY_MODEL_NOT_FOUND")'),
            ('raise AppError(404, "NOT_FOUND", "模型尚未上架，暂时不能调用")', 'raise AppError(404, "GATEWAY_MODEL_UNPUBLISHED")'),
            ('raise AppError(404, "NOT_FOUND", "模型部署已停用，暂时不能调用")', 'raise AppError(404, "GATEWAY_DEPLOYMENT_DISABLED")'),
        ],
    ),
    (
        "apps/api/app/gateway/router.py",
        [
            ('raise AppError(503, "DEPENDENCY_UNAVAILABLE", "数据库未就绪")', 'raise AppError(503, "GATEWAY_DB_NOT_READY")'),
        ],
    ),
    (
        "apps/api/app/providers/service.py",
        [
            ('raise AppError(400, "VALIDATION_ERROR", "供应商类型不支持，请选择列表中的类型")', 'raise AppError(400, "PROVIDER_TYPE_INVALID")'),
            ('raise AppError(400, "VALIDATION_ERROR", "供应商名称不能为空")', 'raise AppError(400, "PROVIDER_NAME_EMPTY")'),
            ('raise AppError(400, "VALIDATION_ERROR", "上游凭证不能为空")', 'raise AppError(400, "PROVIDER_CREDENTIAL_EMPTY")'),
            ('raise AppError(400, "VALIDATION_ERROR", "白名单主机名格式不正确")', 'raise AppError(400, "PROVIDER_ALLOWLIST_HOST_INVALID")'),
            ('raise AppError(404, "NOT_FOUND", "模型不存在")', 'raise AppError(404, "PROVIDER_MODEL_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "部署状态只能是 active（启用）或 disabled（停用）")', 'raise AppError(400, "DEPLOYMENT_STATUS_INVALID")'),
            ('raise AppError(404, "NOT_FOUND", "部署不存在")', 'raise AppError(404, "DEPLOYMENT_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "测试类型不支持，请选择列表中的类型")', 'raise AppError(400, "PROVIDER_TEST_TYPE_INVALID")'),
            ('raise AppError(502, "UPSTREAM_ERROR", "上游没有返回可用响应，请稍后再试或检查凭证与地址")', 'raise AppError(502, "PROVIDER_UPSTREAM_NO_RESPONSE")'),
            ('raise AppError(502, "UPSTREAM_ERROR", "未能读取上游模型清单，请稍后再试或检查连通性")', 'raise AppError(502, "PROVIDER_MODELS_FETCH_FAILED")'),
            ('raise AppError(502, "UPSTREAM_ERROR", "上游返回的模型清单格式无法识别，请核对供应商类型与地址")', 'raise AppError(502, "PROVIDER_MODELS_FORMAT_INVALID")'),
            ('raise AppError(400, "VALIDATION_ERROR", "该供应商还没有可用凭证，请先保存上游密钥")', 'raise AppError(400, "PROVIDER_NO_CREDENTIAL")'),
            ('raise AppError(404, "NOT_FOUND", "供应商不存在")', 'raise AppError(404, "PROVIDER_NOT_FOUND")'),
        ],
    ),
    (
        "apps/api/app/billing/ledger.py",
        [
            ('raise AppError(400, "VALIDATION_ERROR", f"流水类型「{entry_type}」不支持")', 'raise AppError(400, "LEDGER_ENTRY_TYPE_INVALID", details={"entry_type": entry_type})'),
            ('raise AppError(400, "VALIDATION_ERROR", "流水方向只能是 C（入账）、D（出账）或 N")', 'raise AppError(400, "LEDGER_DIRECTION_INVALID")'),
            ('raise AppError(400, "VALIDATION_ERROR", "金额必须大于 0")', 'raise AppError(400, "AMOUNT_POSITIVE")'),
            ('raise AppError(402, "INSUFFICIENT_BALANCE", "可用余额不足，无法完成本次入账或扣减")', 'raise AppError(402, "BALANCE_INSUFFICIENT")'),
            ('raise AppError(400, "VALIDATION_ERROR", "预扣金额必须大于 0")', 'raise AppError(400, "HOLD_AMOUNT_POSITIVE")'),
            ('raise AppError(400, "VALIDATION_ERROR", "预扣有效期必须大于 0 秒")', 'raise AppError(400, "HOLD_TTL_POSITIVE")'),
            ('raise AppError(400, "VALIDATION_ERROR", "结算金额不能为负数")', 'raise AppError(400, "SETTLE_AMOUNT_NEGATIVE")'),
        ],
    ),
    (
        "apps/api/app/billing/money.py",
        [
            ('raise AppError(400, "VALIDATION_ERROR", "金额格式不正确，请输入有效数字")', 'raise AppError(400, "AMOUNT_BAD_FORMAT")'),
            ('raise AppError(400, "VALIDATION_ERROR", "金额格式不正确，请输入有效数字") from exc', 'raise AppError(400, "AMOUNT_BAD_FORMAT") from exc'),
            ('raise AppError(400, "VALIDATION_ERROR", "金额不能为负数")', 'raise AppError(400, "AMOUNT_NEGATIVE")'),
            ('raise AppError(400, "VALIDATION_ERROR", "金额最多支持 8 位小数")', 'raise AppError(400, "AMOUNT_SCALE")'),
            ('raise AppError(400, "VALIDATION_ERROR", "币种代码不正确（例如 USD、CNY）")', 'raise AppError(400, "CURRENCY_INVALID")'),
        ],
    ),
    (
        "apps/api/app/billing/pricing.py",
        [
            ('raise AppError(404, "NOT_FOUND", "模型不存在")', 'raise AppError(404, "BILLING_MODEL_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "至少需要一条单价")', 'raise AppError(400, "PRICE_ITEMS_REQUIRED")'),
            ('raise AppError(400, "VALIDATION_ERROR", f"计量项「{item.meter}」无效")', 'raise AppError(400, "PRICE_METER_INVALID", details={"meter": item.meter})'),
            ('raise AppError(400, "VALIDATION_ERROR", f"计量项「{item.meter}」重复，每条只能出现一次")', 'raise AppError(400, "PRICE_METER_DUPLICATE", details={"meter": item.meter})'),
            ('raise AppError(400, "VALIDATION_ERROR", "最低计费单位不能为负数")', 'raise AppError(400, "PRICE_MIN_UNIT_NEGATIVE")'),
            ('raise AppError(404, "NOT_FOUND", "价格版本不存在")', 'raise AppError(404, "PRICE_VERSION_NOT_FOUND")'),
            ('raise AppError(400, "VALIDATION_ERROR", "单价格式不正确，请输入有效的十进制数字")', 'raise AppError(400, "PRICE_UNIT_BAD_FORMAT")'),
            ('raise AppError(400, "VALIDATION_ERROR", "最低计费单位必须是非负整数")', 'raise AppError(400, "PRICE_MIN_UNIT_INT")'),
        ],
    ),
    (
        "apps/api/app/billing/service.py",
        [
            ('raise AppError(402, "INSUFFICIENT_BALANCE", "密钥预算已用完")', 'raise AppError(402, "KEY_BUDGET_EXHAUSTED")'),
            ('raise AppError(404, "NOT_FOUND", "调用记录不存在")', 'raise AppError(404, "BILLING_USAGE_NOT_FOUND")'),
        ],
    ),
    (
        "apps/api/app/security/ssrf.py",
        [
            ('raise AppError(400, "VALIDATION_ERROR", "域名无法解析") from exc', 'raise AppError(400, "URL_DNS_FAILED") from exc'),
            ('raise AppError(400, "VALIDATION_ERROR", "地址只允许 http 或 https，且不能带账号")', 'raise AppError(400, "URL_SCHEME_INVALID")'),
            ('raise AppError(400, "VALIDATION_ERROR", "地址主机名无效")', 'raise AppError(400, "URL_HOST_INVALID")'),
            ('raise AppError(400, "VALIDATION_ERROR", "云元数据地址被拒绝")', 'raise AppError(400, "URL_METADATA_BLOCKED")'),
            ('raise AppError(400, "VALIDATION_ERROR", "域名无法解析")', 'raise AppError(400, "URL_DNS_FAILED")'),
            ('raise AppError(400, "VALIDATION_ERROR", "自建端点必须先通过白名单")', 'raise AppError(400, "URL_ALLOWLIST_REQUIRED")'),
            ('raise AppError(400, "VALIDATION_ERROR", "重定向次数过多")', 'raise AppError(400, "URL_REDIRECT_LIMIT")'),
        ],
    ),
]


def apply_file(rel: str, pairs: list[tuple[str, str]]) -> None:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old not in text:
            print(f"WARN {rel}: missing {old[:70]!r}")
            continue
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print(f"updated {rel}")


def fix_specials() -> None:
    # ops coupon generate conflict
    p = ROOT / "apps/api/app/ops/service.py"
    t = p.read_text(encoding="utf-8")
    old = '''        raise AppError(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "券码生成遇到冲突，请再点一次自动生成；若持续出现请稍后再试",
        )'''
    new = '        raise AppError(503, "COUPON_GENERATE_CONFLICT")'
    if old in t:
        t = t.replace(old, new)
        p.write_text(t, encoding="utf-8")
        print("ops generate special ok")

    # platform multiline backups
    p = ROOT / "apps/api/app/ops/platform.py"
    t = p.read_text(encoding="utf-8")
    specials = [
        (
            '''        raise AppError(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "当前 DATABASE_URL 不是 PostgreSQL，无法备份。请改用 PostgreSQL 或安装 pg_dump。",
        )''',
            '        raise AppError(503, "BACKUP_NOT_POSTGRES")',
        ),
        (
            '''        raise AppError(
            503,
            "DEPENDENCY_UNAVAILABLE",
            f"备份未完成：{tip}。请核对数据库是否可达、账号是否有导出权限",
        )''',
            '        raise AppError(503, "BACKUP_FAILED", details={"tip": tip})',
        ),
        (
            '''        raise AppError(
            503,
            "DEPENDENCY_UNAVAILABLE",
            f"无法连接数据库做 SQL 备份：{type(exc).__name__}。请确认 PostgreSQL 已启动且 DATABASE_URL 正确",
        ) from exc''',
            '        raise AppError(503, "BACKUP_SQL_CONNECT_FAILED", details={"error": type(exc).__name__}) from exc',
        ),
        (
            '''        raise AppError(
            503,
            "DEPENDENCY_UNAVAILABLE",
            f"SQL 备份未完成：{type(exc).__name__}。请检查账号是否有读表权限",
        ) from exc''',
            '        raise AppError(503, "BACKUP_SQL_FAILED", details={"error": type(exc).__name__}) from exc',
        ),
    ]
    for old, new in specials:
        if old not in t:
            print(f"WARN platform special missing: {old[:50]!r}")
        else:
            t = t.replace(old, new)
            print("platform special ok")
    p.write_text(t, encoding="utf-8")

    # gateway multiline
    p = ROOT / "apps/api/app/gateway/service.py"
    t = p.read_text(encoding="utf-8")
    gspecs = [
        (
            '''                raise AppError(
                    502,
                    "UPSTREAM_ERROR",
                    "上游返回了错误状态，请稍后再试；若持续出现请联系客服",
                )''',
            '                raise AppError(502, "GATEWAY_UPSTREAM_STATUS")',
        ),
        (
            '''                raise AppError(
                    503,
                    "DEPENDENCY_UNAVAILABLE",
                    "暂时连不上模型服务，请稍后再试；若持续出现请联系客服",
                ) from exc''',
            '                raise AppError(503, "GATEWAY_UPSTREAM_UNREACHABLE") from exc',
        ),
    ]
    for old, new in gspecs:
        c = t.count(old)
        if c == 0:
            print(f"WARN gateway special missing: {old[:40]!r}")
        else:
            t = t.replace(old, new)
            print(f"gateway special x{c}")
    p.write_text(t, encoding="utf-8")

    # ssrf private vs allowlist
    p = ROOT / "apps/api/app/security/ssrf.py"
    t = p.read_text(encoding="utf-8")
    old = '''            raise AppError(
                400,
                "VALIDATION_ERROR",
                "自建端点必须先通过白名单" if self_hosted else "地址落在私有或保留网段",
            )'''
    new = '''            raise AppError(
                400,
                "URL_ALLOWLIST_REQUIRED" if self_hosted else "URL_PRIVATE_BLOCKED",
            )'''
    if old in t:
        p.write_text(t.replace(old, new), encoding="utf-8")
        print("ssrf special ok")
    else:
        print("WARN ssrf special missing")

    # gateway router / litellm endpoint messages if any in other files
    for rel in ("apps/api/app/gateway/router.py", "apps/api/app/gateway/openai.py", "apps/api/app/main.py"):
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        n = text
        n = n.replace('raise AppError(400, "VALIDATION_ERROR", "该接口尚未开放")', 'raise AppError(400, "ENDPOINT_NOT_OPEN")')
        n = n.replace('raise AppError(400, "VALIDATION_ERROR", "请求体必须是 JSON")', 'raise AppError(400, "BODY_MUST_BE_JSON")')
        n = n.replace('raise AppError(400, "VALIDATION_ERROR", "请求体必须是 JSON 对象")', 'raise AppError(400, "BODY_MUST_BE_JSON_OBJECT")')
        if n != text:
            path.write_text(n, encoding="utf-8")
            print(f"endpoint msgs {rel}")


def inject_catalog() -> None:
    # backend
    path = ROOT / "apps/api/app/core/errors.py"
    text = path.read_text(encoding="utf-8")
    # find last entry before closing MESSAGE_BY_CODE
    end = text.find("\n}\n\n\nclass AppError")
    if end < 0:
        end = text.find("\n}\n\nclass AppError")
    if end < 0:
        raise SystemExit("cannot find MESSAGE_BY_CODE end")
    # insert before }
    insert_at = end
    lines = []
    for code, (zh, _en, _tw) in CATALOG.items():
        if f'"{code}":' in text:
            continue
        lines.append(f'    "{code}": "{zh}",')
    if lines:
        text = text[:insert_at] + "\n" + "\n".join(lines) + text[insert_at:]
        path.write_text(text, encoding="utf-8")
        print(f"backend +{len(lines)}")
    else:
        print("backend all present")

    for locale, idx in (("zh-CN", 0), ("en", 1), ("zh-TW", 2)):
        fpath = ROOT / f"apps/web/src/content/{locale}.ts"
        ftext = fpath.read_text(encoding="utf-8")
        start = ftext.find("  errors: {")
        if start < 0:
            raise SystemExit(f"no errors in {locale}")
        # end of errors object: next top-level after errors
        # find COUPON_EXHAUSTED or last known, then },
        # safer: find matching close by scanning from errors
        i = ftext.find("{", start)
        depth = 0
        end_i = None
        for j in range(i, len(ftext)):
            ch = ftext[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_i = j
                    break
        if end_i is None:
            raise SystemExit(f"errors end {locale}")
        chunk = ftext[start:end_i]
        extra = []
        for code, vals in CATALOG.items():
            if f"{code}:" in chunk:
                continue
            msg = vals[idx].replace("\\", "\\\\").replace('"', '\\"')
            extra.append(f'    {code}: "{msg}",')
        if not extra:
            print(f"{locale} all present")
            continue
        ftext = ftext[:end_i] + "\n" + "\n".join(extra) + "\n" + ftext[end_i:]
        fpath.write_text(ftext, encoding="utf-8")
        print(f"{locale} +{len(extra)}")


def main() -> None:
    for rel, pairs in REPLACEMENTS:
        apply_file(rel, pairs)
    fix_specials()
    inject_catalog()
    print("done")


if __name__ == "__main__":
    main()
