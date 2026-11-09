"""统一错误码与响应信封。错误码基线见需求附录 A，此处不得删除既有码。"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CODE_BY_STATUS: dict[int, str] = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHENTICATED",
    402: "INSUFFICIENT_BALANCE",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "IDEMPOTENCY_CONFLICT",
    429: "RATE_LIMITED",
    500: "INTERNAL",
    502: "UPSTREAM_ERROR",
    503: "DEPENDENCY_UNAVAILABLE",
}

MESSAGE_BY_CODE: dict[str, str] = {
    "VALIDATION_ERROR": "填写内容有误，请核对后重试",
    "UNAUTHENTICATED": "尚未登录，或登录已过期，请重新登录",
    "INVALID_API_KEY": "API Key 不正确或已失效",
    "FORBIDDEN": "当前账号没有执行此操作的权限",
    "INSUFFICIENT_BALANCE": "余额或密钥预算不足",
    "NOT_FOUND": "未找到对应内容",
    "IDEMPOTENCY_CONFLICT": "操作冲突，请刷新页面后重试",
    "RATE_LIMITED": "操作过于频繁，请稍后再试",
    "CONCURRENCY_LIMITED": "当前并发已满，请稍后再试",
    # 程序/依赖类：对客户语气柔和，细节看日志与 request_id
    "UPSTREAM_ERROR": "上游服务暂时繁忙，请稍后再试；若持续出现请联系客服",
    "DEPENDENCY_UNAVAILABLE": "系统暂时繁忙，请稍后再试；若持续出现请联系客服",
    "INTERNAL": "刚才出了点小状况，请稍后再试；若持续出现请联系客服并告知请求编号",
    "METHOD_NOT_ALLOWED": "当前地址不支持该请求方法",
    "EMAIL_TAKEN": "该邮箱已注册",
    "EMAIL_NOT_VERIFIED": "邮箱尚未验证，请先完成邮箱验证",
    "ACCOUNT_LOCKED": "登录失败次数过多，账号已暂时锁定，请稍后再试",
    "MAIL_NOT_CONFIGURED": "邮件服务尚未配置，暂时无法发送邮件",
    "TOKEN_INVALID": "验证码或链接无效；若已过期请重新获取",
    # 优惠券兑换：稳定码供前端按语言映射；message 仍作默认中文兜底
    "COUPON_EMPTY": "请输入优惠券码",
    "COUPON_BAD_FORMAT": "券码格式不正确",
    "COUPON_NOT_FOUND": "优惠券不存在，请核对券码是否完整、是否输错",
    "COUPON_DELETED": "优惠券已删除，无法兑换",
    "COUPON_DISABLED": "优惠券已停用，暂时无法兑换",
    "COUPON_CURRENCY": "这张优惠券币种与当前结算币不一致，无法兑换",
    "COUPON_EXPIRED": "优惠券已过期，无法兑换",
    "COUPON_ALREADY_REDEEMED": "这张优惠券你已经兑换过了，每个账号只能兑一次",
    "COUPON_EXHAUSTED": "优惠券兑换名额已用完",
    "AUTH_TERMS_REQUIRED": "需要同意服务条款和隐私政策",
    "AUTH_REGISTER_RATE_LIMITED": "当前网络注册过于频繁，请稍后再试",
    "AUTH_BAD_CREDENTIALS": "邮箱或密码不正确",
    "ACCOUNT_FROZEN": "账号已冻结",
    "AUTH_TOTP_CHALLENGE_EXPIRED": "二次验证已失效，请重新登录",
    "AUTH_TOTP_BAD_CODE": "验证码不正确",
    "PROFILE_NOT_FOUND": "资料不存在",
    "LOCALE_INVALID": "语言只能是 zh-CN、zh-TW 或 en",
    "TIMEZONE_INVALID": "时区名称无法识别，请使用如 Asia/Shanghai 的标准时区",
    "SESSION_NOT_FOUND": "会话不存在",
    "AUTH_BAD_CURRENT_PASSWORD": "当前密码不正确",
    "EMAIL_SAME_AS_CURRENT": "新邮箱与当前邮箱相同",
    "EMAIL_INVALID": "邮箱格式不正确",
    "PASSWORD_LENGTH": "密码长度需要在 10 到 128 之间",
    "PASSWORD_COMPLEXITY": "密码需要同时包含字母和数字",
    "PASSWORD_COMMON": "密码过于常见",
    "TOTP_ALREADY_ENABLED": "二次验证已开启",
    "TOTP_SEED_REQUIRED": "请先生成二次验证种子",
    "TOTP_DECRYPT_FAILED": "二次验证信息暂时无法读取，请稍后再试或联系客服",
    "CREDENTIAL_DECRYPT_FAILED": "上游凭证暂时无法读取，请稍后再试或联系客服",
    "ORIGIN_FORBIDDEN": "当前来源地址不被允许访问此接口",
    "BOOTSTRAP_TOKEN_USED": "初始化口令已被使用，超级管理员应已创建",
    "BOOTSTRAP_TOKEN_MISSING": "初始化口令文件不存在，请先按文档生成",
    "BOOTSTRAP_TOKEN_INVALID": "初始化口令不正确",
    "BOOTSTRAP_ALREADY_DONE": "超级管理员已存在，无需再次初始化",
    "ROLE_SUPERADMIN_FORBIDDEN": "不能通过该接口分配超级管理员",
    "ROLE_NOT_FOUND": "角色不存在",
    "USER_NOT_FOUND": "用户不存在",
    "MAIL_SEND_RATE_LIMITED": "发送过于频繁，请稍后再试",
    "MAIL_DAILY_LIMIT": "今日发送次数已达上限",
    "MAIL_SEND_FAILED": "邮件暂时发不出去，请稍后再试；若持续出现请联系客服",
    "TOKEN_TOO_MANY_ATTEMPTS": "尝试验证次数过多，请重新获取新的链接或令牌",
    "TOKEN_EXPIRED": "验证链接或令牌已过期，请重新获取",
    "TOKEN_MISMATCH": "验证码或令牌不正确",
    "IDEMPOTENCY_KEY_REQUIRED": "请在请求头提供 Idempotency-Key，避免重复下单",
    "IDEMPOTENCY_KEY_REUSED": "重复提交：该幂等键已被使用，请更换后重试",
    "IDEMPOTENCY_KEY_INVALID": "请提供合法的 Idempotency-Key（1～80 个字符）",
    "IDEMPOTENCY_PAYLOAD_MISMATCH": "同一幂等键对应的请求内容不一致，请更换键后重试",
    "PRODUCT_NOT_FOUND": "充值套餐不存在",
    "PRODUCT_DELETED": "充值套餐已删除，不能购买",
    "PRODUCT_DISABLED": "充值套餐已停用，暂时不能购买",
    "PRODUCT_CURRENCY_MISMATCH": "该套餐币种与当前结算币不一致，不能购买",
    "ORDER_NOT_FOUND": "订单不存在",
    "ORDER_EXPIRED": "订单已过期，请重新下单",
    "ORDER_STATUS_FILTER_INVALID": "订单状态「{status}」不支持筛选",
    "ORDER_CONFIRM_STATUS_INVALID": "订单当前状态为「{status}」，不能再确认",
    "RECONCILE_STATUS_INVALID": "对账状态只能是 unchecked / matched / disputed",
    "RECONCILE_ORDER_NOT_CREDITED": "只有已入账订单（已完成/多付）才能标记对账结果",
    "RECONCILE_CHANNEL_INVALID": "不支持的对账渠道「{channel}」",
    "MOCK_PAYMENTS_DISABLED": "当前环境未开启模拟支付",
    "MOCK_CHANNEL_REQUIRED": "该订单不是模拟支付渠道，不能用模拟确认",
    "REFUND_NOT_FOUND": "退款单不存在",
    "REFUND_ORDER_NOT_CREDITED": "订单状态为「{status}」，尚未入账，不能退款",
    "REFUND_USDT_DESTINATION": "USDT 退款只能退回原付款地址",
    "REFUND_ALREADY_EXISTS": "该订单已有退款单，不能重复发起",
    "REFUND_NOT_PENDING_REVIEW": "退款单当前状态为「{status}」，不是待复核，不能复核",
    "REFUND_REJECT_STATUS_INVALID": "退款单当前状态为「{status}」，只能拒绝待复核或已复核待执行的单",
    "REFUND_SELF_REVIEW_FORBIDDEN": "退款发起人不能复核自己的单，请换另一名财务",
    "REFUND_SELF_REJECT_FORBIDDEN": "退款发起人不能拒绝自己的单，请换另一名财务",
    "REFUND_NOT_REVIEWED": "退款单当前状态为「{status}」，须先完成复核再执行",
    "REFUND_EXECUTOR_MUST_BE_THIRD": "退款执行人必须是发起人、复核人之外的第三人",
    "FX_DEVIATION_TOO_HIGH": "当前汇率偏离过大，已拒绝下单，请稍后再试",
    "USDT_ADDRESS_UNCONFIGURED": "USDT 固定收款地址尚未配置，暂时无法下单",
    "USDT_TAIL_POOL_FULL": "USDT 尾数池已满，请稍后再试或换其他渠道",
    "USDT_AMOUNT_TOO_LOW": "低于 USDT 最低充值金额（当前最低 {min_amount}）",
    "CHANNEL_NOT_ALLOWED_OVERSEAS": "海外模式不能使用微信/支付宝，请改用 Stripe 或 USDT",
    "CHANNEL_NOT_ALLOWED_CN": "大陆模式不能使用 Stripe/USDT，请改用微信或支付宝",
    "CHANNEL_UNSUPPORTED": "不支持的支付渠道「{channel}」",
    "CHANNEL_NOT_CONFIGURED": "「{channel}」支付渠道尚未配置，暂时无法下单",
    "KEY_NAME_INVALID": "密钥名称需要在 1 到 128 个字符之间",
    "KEY_STATUS_INVALID": "密钥状态不支持，请使用列表中的状态",
    "KEY_NOT_FOUND": "密钥不存在",
    "KEY_EXPIRES_BAD_FORMAT": "到期时间格式不正确，请使用带时区的 ISO 时间",
    "KEY_EXPIRES_TZ_REQUIRED": "到期时间必须带时区（例如以 Z 或 +08:00 结尾）",
    "KEY_BUDGET_BAD_FORMAT": "预算必须是有效的十进制数字",
    "KEY_BUDGET_POSITIVE": "预算必须大于 0",
    "SORT_FIELD_INVALID": "排序字段不支持，请使用列表中的字段名",
    "SETTLEMENT_STATUS_INVALID": "结算状态不支持，请使用列表中的状态",
    "API_KEY_BAD_FORMAT": "API Key 格式不正确（应以 sk- 开头）",
    "API_KEY_INVALID": "API Key 已失效（可能已吊销或已过期）",
    "API_KEY_MISSING": "API Key 不存在",
    "API_KEY_REVOKED": "API Key 已删除（吊销），不能再使用",
    "API_KEY_EXPIRED": "API Key 已过期",
    "API_KEY_DISABLED": "API Key 已停用，暂时不能调用；可在控制台重新启用",
    "API_KEY_STATUS_INVALID": "API Key 当前状态为「{status}」，不能使用",
    "API_KEY_IP_DENIED": "来源 IP 不在该密钥的白名单中",
    "API_KEY_BUDGET_EXCEEDED": "该密钥的预算已用完，请提高预算或更换密钥",
    "API_KEY_MODEL_DENIED": "该密钥无权调用此模型，请在密钥权限中勾选该模型",
    "USAGE_NOT_FOUND": "调用记录不存在",
    "TICKET_CATEGORY_INVALID": "工单分类不支持，请选择列表中的分类",
    "TICKET_EMPTY": "工单标题和内容不能为空",
    "TICKET_REPLY_EMPTY": "回复不能为空",
    "TICKET_STATUS_INVALID": "工单状态不支持，请选择列表中的状态",
    "TICKET_CLOSED": "已关闭的工单不能再回复",
    "TICKET_NOT_FOUND": "工单不存在",
    "INVOICE_ORDER_NOT_FOUND": "可开票的订单不存在（须为已支付订单）",
    "INVOICE_TITLE_EMPTY": "发票抬头不能为空",
    "INVOICE_ALREADY_REQUESTED": "该订单已申请过发票",
    "INVOICE_STATUS_INVALID": "发票状态不支持，请选择待开票、已开票或已拒绝",
    "INVOICE_NOT_FOUND": "发票申请不存在",
    "INVOICE_ALREADY_REVIEWED": "这张发票已经处理过，不能重复审核",
    "ANNOUNCEMENT_EMPTY": "公告标题和正文不能为空",
    "ANNOUNCEMENT_SLUG_TAKEN": "公告地址已被使用",
    "ANNOUNCEMENT_NOT_FOUND": "公告不存在",
    "ANNOUNCEMENT_SLUG_INVALID": "公告地址只能用小写字母、数字和连字符",
    "COUPON_BONUS_POSITIVE": "赠送金额必须大于 0",
    "COUPON_MAX_USES_MIN": "可用次数至少为 1",
    "COUPON_CODE_EXISTS": "该优惠券码已存在，请换一个或使用自动生成",
    "COUPON_ADMIN_NOT_FOUND": "优惠券不存在",
    "COUPON_GENERATE_CONFLICT": "券码生成遇到冲突，请再点一次自动生成；若持续出现请稍后再试",
    "STATUS_FILTER_INVALID": "状态筛选只能是 active / disabled / all",
    "BACKUP_NOT_POSTGRES": "当前 DATABASE_URL 不是 PostgreSQL，无法备份。请改用 PostgreSQL 或安装 pg_dump。",
    "BACKUP_DB_URL_INCOMPLETE": "数据库地址无法用于备份：缺少库名或用户名",
    "BACKUP_TOOL_MISSING": "找不到备份程序，请检查 PG_DUMP_PATH 或 Docker",
    "BACKUP_TIMEOUT": "备份超时（超过 180 秒），请检查数据库负载后重试",
    "BACKUP_FAILED": "备份未完成：{tip}。请核对数据库是否可达、账号是否有导出权限",
    "BACKUP_DOCKER_MISSING": "本机没有 Docker，无法回退备份",
    "BACKUP_SQL_CONNECT_FAILED": "无法连接数据库做 SQL 备份：{error}。请确认 PostgreSQL 已启动且 DATABASE_URL 正确",
    "BACKUP_SQL_FAILED": "SQL 备份未完成：{error}。请检查账号是否有读表权限",
    "BACKUP_EMPTY_FILE": "备份文件未生成或大小为 0，请检查权限与磁盘空间",
    "BACKUP_NAME_INVALID": "备份文件名不合法（仅允许 .dump / .sql）",
    "BACKUP_FILE_NOT_FOUND": "备份文件不存在",
    "GATEWAY_DB_NOT_READY": "数据库未就绪",
    "GATEWAY_MODEL_REQUIRED": "必须提供模型名称",
    "GATEWAY_KEY_USER_MISSING": "密钥所属账号不存在",
    "GATEWAY_ACCOUNT_UNAVAILABLE": "账号已冻结或不可用，暂时不能调用",
    "GATEWAY_EMBEDDINGS_UNSUPPORTED": "该模型未确认支持 embeddings，请换用支持向量的模型",
    "GATEWAY_RPM_LIMIT": "请求过于频繁（已达每分钟次数上限），请稍后再试",
    "GATEWAY_TPM_LIMIT": "请求过于频繁（已达每分钟 Token 上限），请稍后再试",
    "GATEWAY_CONCURRENCY_LIMIT": "当前并发已满，请等待进行中的请求结束后再试",
    "GATEWAY_UPSTREAM_STATUS": "上游返回了错误状态，请稍后再试；若持续出现请联系客服",
    "GATEWAY_UPSTREAM_UNREADABLE": "上游响应暂时无法读取，请稍后再试",
    "GATEWAY_MODEL_NOT_FOUND": "模型不存在",
    "GATEWAY_MODEL_UNPUBLISHED": "模型尚未上架，暂时不能调用",
    "GATEWAY_DEPLOYMENT_DISABLED": "模型部署已停用，暂时不能调用",
    "GATEWAY_UPSTREAM_UNREACHABLE": "暂时连不上模型服务，请稍后再试；若持续出现请联系客服",
    "ENDPOINT_NOT_OPEN": "该接口尚未开放",
    "BODY_MUST_BE_JSON": "请求体必须是 JSON",
    "BODY_MUST_BE_JSON_OBJECT": "请求体必须是 JSON 对象",
    "PROVIDER_TYPE_INVALID": "供应商类型不支持，请选择列表中的类型",
    "PROVIDER_NAME_EMPTY": "供应商名称不能为空",
    "PROVIDER_CREDENTIAL_EMPTY": "上游凭证不能为空",
    "PROVIDER_ALLOWLIST_HOST_INVALID": "白名单主机名格式不正确",
    "PROVIDER_MODEL_NOT_FOUND": "模型不存在",
    "DEPLOYMENT_STATUS_INVALID": "部署状态只能是 active（启用）或 disabled（停用）",
    "DEPLOYMENT_NOT_FOUND": "部署不存在",
    "PROVIDER_TEST_TYPE_INVALID": "测试类型不支持，请选择列表中的类型",
    "PROVIDER_UPSTREAM_NO_RESPONSE": "上游没有返回可用响应，请稍后再试或检查凭证与地址",
    "PROVIDER_MODELS_FETCH_FAILED": "未能读取上游模型清单，请稍后再试或检查连通性",
    "PROVIDER_MODELS_FORMAT_INVALID": "上游返回的模型清单格式无法识别，请核对供应商类型与地址",
    "PROVIDER_NO_CREDENTIAL": "该供应商还没有可用凭证，请先保存上游密钥",
    "PROVIDER_NOT_FOUND": "供应商不存在",
    "LEDGER_ENTRY_TYPE_INVALID": "流水类型「{entry_type}」不支持",
    "LEDGER_DIRECTION_INVALID": "流水方向只能是 C（入账）、D（出账）或 N",
    "AMOUNT_POSITIVE": "金额必须大于 0",
    "BALANCE_INSUFFICIENT": "可用余额不足，无法完成本次入账或扣减",
    "HOLD_AMOUNT_POSITIVE": "预扣金额必须大于 0",
    "HOLD_TTL_POSITIVE": "预扣有效期必须大于 0 秒",
    "SETTLE_AMOUNT_NEGATIVE": "结算金额不能为负数",
    "AMOUNT_BAD_FORMAT": "金额格式不正确，请输入有效数字",
    "AMOUNT_NEGATIVE": "金额不能为负数",
    "AMOUNT_SCALE": "金额最多支持 8 位小数",
    "CURRENCY_INVALID": "币种代码不正确（例如 USD、CNY）",
    "BILLING_MODEL_NOT_FOUND": "模型不存在",
    "PRICE_ITEMS_REQUIRED": "至少需要一条单价",
    "PRICE_METER_INVALID": "计量项「{meter}」无效",
    "PRICE_METER_DUPLICATE": "计量项「{meter}」重复，每条只能出现一次",
    "PRICE_MIN_UNIT_NEGATIVE": "最低计费单位不能为负数",
    "PRICE_VERSION_NOT_FOUND": "价格版本不存在",
    "PRICE_UNIT_BAD_FORMAT": "单价格式不正确，请输入有效的十进制数字",
    "PRICE_MIN_UNIT_INT": "最低计费单位必须是非负整数",
    "KEY_BUDGET_EXHAUSTED": "密钥预算已用完",
    "BILLING_USAGE_NOT_FOUND": "调用记录不存在",
    "URL_DNS_FAILED": "域名无法解析",
    "URL_SCHEME_INVALID": "地址只允许 http 或 https，且不能带账号",
    "URL_HOST_INVALID": "地址主机名无效",
    "URL_METADATA_BLOCKED": "云元数据地址被拒绝",
    "URL_ALLOWLIST_REQUIRED": "自建端点必须先通过白名单",
    "URL_PRIVATE_BLOCKED": "地址落在私有或保留网段",
    "URL_REDIRECT_LIMIT": "重定向次数过多",
    "ADMIN_BUDGET_POSITIVE": "预算必须大于 0",
    "SANCTION_PATCH_EMPTY": "请至少提供要修改的来源或原因说明",
    "SANCTION_NETWORK_INVALID": "网络不支持：请填写支持的链类型",
    "SANCTION_ADDRESS_REQUIRED": "请填写链上地址",
    "SANCTION_ADDRESS_TOO_LONG": "地址过长（最多 {max} 个字符）",
    "SANCTION_ERC20_HEX": "ERC20 地址须为十六进制（可带 0x 前缀）",
    "SANCTION_ERC20_LENGTH": "ERC20 地址应为 40 位十六进制（不含 0x 时）",
    "SANCTION_TRC20_WHITESPACE": "TRC20 地址不能包含空白字符",
    "SANCTION_TRC20_PREFIX": "TRC20 地址通常以 T 开头，请核对是否粘贴完整",
    "SANCTION_TRC20_LENGTH": "TRC20 地址长度异常，请核对是否粘贴完整",
    "SANCTION_SOURCE_REQUIRED": "请填写来源（例如 OFAC SDN、人工录入、网关同步）",
    "SANCTION_SOURCE_TOO_LONG": "来源过长（最多 {max} 个字符）",
    "SANCTION_REASON_TOO_LONG": "原因说明过长（最多 {max} 个字符）",
    "SANCTION_ALREADY_EXISTS": "该地址已在「{network}」制裁名单中（来源：{source}）。如需改说明请编辑，勿重复添加。",
    "SANCTION_NOT_FOUND": "制裁地址不存在（可能已删除）",
    "SANCTION_SOURCE_EMPTY": "来源不能为空",
    "USER_FILTER_STATUS_INVALID": "筛选状态不正确，只能是正常或冻结",
    "USER_SEARCH_TOO_LONG": "搜索关键字过长",
    "USER_STATUS_INVALID": "只能改为正常或冻结",
    "USER_CANNOT_FREEZE_SELF": "不能冻结自己的账号",
    "USER_STATUS_TYPE_FORBIDDEN": "该账号类型不能在此改状态（例如已注销账号）",
    "USER_CANNOT_DELETE_SELF": "不能注销自己的账号",
    "USER_DELETE_TYPE_FORBIDDEN": "这个账号不能在这里注销",
    "KEY_IMMUTABLE_DELETED": "已删除或已过期的密钥不能修改，请新建密钥",
    "KEY_STATUS_TOGGLE_FORBIDDEN": "当前密钥状态不能切换启用/停用",
    "KEY_DISABLED_EDIT_FORBIDDEN": "已停用的密钥请先启用后再修改名称或限额；删除请用删除接口",
    "ALLOWLIST_NOT_FOUND": "白名单条目不存在",
    "PROVIDER_NAME_REQUIRED": "名称不能为空",
    "PROVIDER_BASE_URL_INVALID": "基础地址无效：须为完整的 http(s) URL",
    "PROVIDER_DELETED_IMMUTABLE": "供应商已删除，不能修改；请先恢复",
    "CREDENTIAL_NOT_FOUND": "凭证不存在",
    "ROLE_USER_REVOKE_FORBIDDEN": "不能撤销基础用户角色",
    "COUPON_DELETED_IMMUTABLE": "优惠券已删除，不能修改或启用/停用；请先恢复",
    "COUPON_MAX_USES_INVALID": "可兑换总次数无效：须为正整数，且不能小于已兑换次数",
    "ANNOUNCEMENT_TITLE_EMPTY": "标题不能为空",
    "ANNOUNCEMENT_BODY_EMPTY": "内容不能为空",
    "INVOICE_CANCEL_PENDING_ONLY": "只能撤销待审核的发票申请",
    "PRODUCT_DELETED_IMMUTABLE": "套餐已删除，不能修改或启用/停用；请先恢复",
    "LEDGER_ADJUST_DIRECTION": "方向只能是 C 或 D",
    "LEDGER_ADJUST_REASON_REQUIRED": "请填写调账原因",
    "ORDER_CANCEL_PENDING_ONLY": "只能取消待支付订单",
    "ORDER_CLOSE_PENDING_ONLY": "只能关闭待支付订单",
    "PRODUCT_RESTORE_NOT_DELETED": "套餐未删除，无需恢复；请用启用/停用",
    "COUPON_RESTORE_NOT_DELETED": "优惠券未删除，无需恢复；请用启用/停用",
    "PROVIDER_RESTORE_NOT_DELETED": "只有已删除的供应商可以恢复；当前请用启用/停用",
    "IDEMPOTENCY_KEY_REQUIRED_GENERIC": "请在请求头提供 Idempotency-Key，避免重复提交",
    "DB_NOT_READY": "数据库未就绪",
    "NOTIFICATION_NOT_FOUND": "通知不存在",
    "BALANCE_ALERT_THRESHOLD_INVALID": "预警金额无效，较高线不能低于较低线",
}


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message or MESSAGE_BY_CODE.get(code, "操作未成功，请稍后再试")
        self.details = details or {}
        super().__init__(self.message)


def request_id_from(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def envelope(
    *,
    ok: bool,
    request_id: str,
    data: Any = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"ok": ok, "data": data, "error": error, "request_id": request_id}


def success(request: Request, data: Any) -> dict[str, Any]:
    return envelope(ok=True, request_id=request_id_from(request), data=data, error=None)


def failure(
    request: Request,
    status_code: int,
    code: str,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    data: Any = None,
) -> JSONResponse:
    body = envelope(
        ok=False,
        request_id=request_id_from(request),
        data=data,
        error={
            "code": code,
            "message": message or MESSAGE_BY_CODE.get(code, "操作未成功，请稍后再试"),
            "details": details or {},
        },
    )
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: Any) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return failure(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"loc": [str(part) for part in err.get("loc", [])], "msg": err.get("msg", "")}
            for err in exc.errors()
        ]
        return failure(request, 400, "VALIDATION_ERROR", details={"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = CODE_BY_STATUS.get(exc.status_code, "VALIDATION_ERROR" if exc.status_code < 500 else "INTERNAL")
        message = MESSAGE_BY_CODE.get(code, "操作未成功，请稍后再试")
        if exc.status_code == 405:
            return failure(request, exc.status_code, "METHOD_NOT_ALLOWED")
        return failure(request, exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        import structlog

        structlog.get_logger("forgeapi").error("unhandled", error_type=type(exc).__name__)
        return failure(request, 500, "INTERNAL")
