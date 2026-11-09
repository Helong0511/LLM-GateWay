"""对外响应模型。金额字段在后续阶段使用十进制字符串，不使用 float。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class HealthData(BaseModel):
    status: str


class ReadyData(BaseModel):
    status: str
    checks: dict[str, str]


class MetaData(BaseModel):
    product: str
    operating_mode: str
    app_env: str
    mock_payments_enabled: bool
    demo_models_enabled: bool


class HealthResponse(BaseModel):
    ok: bool
    data: HealthData | None = None
    error: ErrorBody | None = None
    request_id: str


class ReadyResponse(BaseModel):
    ok: bool
    data: ReadyData | None = None
    error: ErrorBody | None = None
    request_id: str


class MetaResponse(BaseModel):
    ok: bool
    data: MetaData | None = None
    error: ErrorBody | None = None
    request_id: str
