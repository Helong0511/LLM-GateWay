"""进程配置。只通过 pydantic-settings 读取环境变量。"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "staging", "production"]
OperatingMode = Literal["mainland", "overseas"]

_DEV_MARKERS = ("dev-only", "change-me", "forge-dev-only")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnv = "development"
    operating_mode: OperatingMode = "overseas"
    app_name: str = "forgeapi"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    log_json: bool | None = None

    database_url: str = "postgresql+asyncpg://forge:forge-dev-only@127.0.0.1:5432/forge"
    redis_url: str = "redis://127.0.0.1:6379/0"

    session_secret: str = "dev-only-session-secret-change-me-32bytes"
    encryption_master_key: str = "dev-only-encryption-master-key-32bytes"

    mock_payments_enabled: bool = True
    demo_models_enabled: bool = True
    stripe_webhook_secret: str = "dev-only-stripe-webhook-secret-32bytes"
    usdt_webhook_secret: str = "dev-only-usdt-webhook-secret-32bytes"
    usdt_callback_ips: str = ""
    usdt_shared_address: str = ""
    usdt_address_mode: Literal["unique", "tail"] = "unique"
    usdt_min_amount: Decimal = Decimal("5")
    rate_deviation_limit: Decimal = Decimal("0.02")
    hold_ttl_seconds: int = 600
    payment_ttl_seconds: int = 1800
    # 上游未返回单价时，同步写入的建议价（每 token，结算币）
    default_model_input_price: Decimal = Decimal("0.00000100")
    default_model_output_price: Decimal = Decimal("0.00000200")

    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    max_body_bytes: int = Field(default=4 * 1024 * 1024, ge=1)

    litellm_base_url: str = "http://127.0.0.1:4000"
    litellm_master_key: str = "sk-dev-only-litellm-master-key"

    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@localhost"
    smtp_tls: bool = False

    cookie_secure: bool = False
    terms_version: str = "2026-10-28"
    privacy_version: str = "2026-10-28"
    public_app_url: str = "http://127.0.0.1:3000"
    admin_init_token_path: str = ".data/admin_init_token.sha256"
    # 登录会话：空闲超时会滑动续期，但绝不超过绝对上限。
    # 默认 12 小时无操作需重新登录；即使持续使用，最长 7 天也必须重新登录。
    session_idle_hours: int = 12
    session_absolute_hours: int = 168
    register_ip_hourly_limit: int = 20

    # 备份：优先使用本机/容器内 pg_dump；找不到时可回退到一次性 Docker 镜像执行
    pg_dump_path: str = ""
    backup_docker_image: str = "postgres:16.10-alpine"
    backup_allow_docker: bool = True

    @field_validator("operating_mode", "app_env", mode="before")
    @classmethod
    def _strip_lower(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.app_env != "production":
            return self
        problems: list[str] = []
        if self.mock_payments_enabled:
            problems.append("production 禁止启用 mock 支付")
        if self.demo_models_enabled:
            problems.append("production 禁止启用演示模型")
        if self._looks_like_dev_secret(self.session_secret) or len(self.session_secret) < 32:
            problems.append("production 必须设置独立高强度 SESSION_SECRET")
        if self._looks_like_dev_secret(self.encryption_master_key) or len(self.encryption_master_key) < 32:
            problems.append("production 必须设置 ENCRYPTION_MASTER_KEY")
        if self._looks_like_dev_secret(self.database_url):
            problems.append("production 数据库连接串不得使用开发口令")
        if self._looks_like_dev_secret(self.litellm_master_key):
            problems.append("production 不得使用开发用 LITELLM_MASTER_KEY")
        if self._looks_like_dev_secret(self.stripe_webhook_secret):
            problems.append("production 必须设置 STRIPE_WEBHOOK_SECRET")
        if self.operating_mode == "overseas" and self._looks_like_dev_secret(self.usdt_webhook_secret):
            problems.append("production 必须设置 USDT_WEBHOOK_SECRET")
        if "testclient" in self.usdt_callback_ips.lower():
            problems.append("production 的 USDT 回调白名单不能包含 testclient")
        if problems:
            raise ValueError("；".join(problems))
        return self

    @staticmethod
    def _looks_like_dev_secret(value: str) -> bool:
        lowered = value.lower()
        return any(marker in lowered for marker in _DEV_MARKERS)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def session_cookie_name(self) -> str:
        if self.app_env == "production":
            return "__Host-session"
        return "session"

    @property
    def json_logs(self) -> bool:
        if self.log_json is not None:
            return self.log_json
        return self.app_env != "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
