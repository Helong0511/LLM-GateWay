"""供应商与模型目录。路径不带版本段，响应不含凭证明文。"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import assert_browser_origin, get_current_user, require_permission
from app.billing.money import format_money
from app.core.errors import success
from app.db.models.auth import User
from app.db.session import get_db
from app.providers.service import ProviderService
from app.security.ssrf import default_resolver

router = APIRouter(prefix="/api/admin", tags=["providers"], dependencies=[Depends(assert_browser_origin)])
catalog_router = APIRouter(tags=["catalog"], dependencies=[Depends(assert_browser_origin)])


class ProviderBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str
    base_url: str = Field(min_length=8, max_length=2048)


class CredentialBody(BaseModel):
    label: str = Field(default="default", max_length=128)
    secret: str = Field(min_length=1, max_length=4096)


class AllowlistBody(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    note: str = Field(default="", max_length=256)


class PublishBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    supports_stream: bool
    supports_embeddings: bool


class PublishBatchBody(BaseModel):
    model_ids: list[UUID] = Field(min_length=1, max_length=500)
    supports_stream: bool = True
    supports_embeddings: bool = False


class UnpublishBatchBody(BaseModel):
    model_ids: list[UUID] = Field(min_length=1, max_length=500)


class ProbeBody(BaseModel):
    mode: str


class SyncBody(BaseModel):
    """同步时可对上游输出价加价（百分比），写入建议价。"""

    output_markup_percent: float = Field(default=10, ge=0, le=1000)


class DeploymentStatusBody(BaseModel):
    status: Literal["active", "disabled"]


class DeploymentStatusBatchBody(BaseModel):
    deployment_ids: list[UUID] = Field(min_length=1, max_length=500)
    status: Literal["active", "disabled"]


def _service(request: Request, db: AsyncSession) -> ProviderService:
    resolver = getattr(request.app.state, "ssrf_resolver", default_resolver)
    client = getattr(request.app.state, "upstream_client", None)
    # transport 用于测试/私有链路注入，与服务内部 client 是两个独立入口：
    # 早前误把 AsyncClient 当 transport 传，isinstance 恒 False，注入通道被静默丢弃。
    transport = getattr(request.app.state, "upstream_transport", None)
    if not isinstance(transport, httpx.AsyncBaseTransport):
        transport = None
    return ProviderService(
        db, request.app.state.clock, request.app.state.settings, resolver, transport, upstream_client=client
    )


@catalog_router.get("/api/console/models")
async def console_models(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    _ = user
    rows = await _service(request, db).list_models(published_only=True)
    return success(request, {"models": rows, "note": "capabilities_unconfirmed"})


@router.get("/providers/presets")
async def provider_presets(
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    _ = user
    _ = db
    return success(request, {"presets": ProviderService.presets()})


@router.post("/providers")
async def create_provider(
    body: ProviderBody,
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).create(user.id, body.name, body.kind, body.base_url)
    return success(request, data)


@router.get("/providers")
async def list_providers(
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    _ = user
    rows = await _service(request, db).list_providers()
    return success(request, {"providers": rows})


@router.post("/providers/{provider_id}/credentials")
async def add_credential(
    provider_id: UUID,
    body: CredentialBody,
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).add_credential(user.id, provider_id, body.label, body.secret)
    return success(request, data)


@router.post("/allowlist")
async def approve_allowlist(
    body: AllowlistBody,
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).approve_host(user.id, body.host, body.note)
    return success(request, data)


@router.post("/providers/{provider_id}/sync")
async def sync_provider(
    provider_id: UUID,
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
    body: SyncBody | None = None,
) -> dict[str, object]:
    markup = SyncBody().output_markup_percent if body is None else body.output_markup_percent
    data = await _service(request, db).sync_models(
        user.id,
        provider_id,
        output_markup_percent=markup,
    )
    return success(request, data)


@router.get("/models")
async def list_models(
    request: Request,
    user: User = Depends(require_permission("model:publish")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    _ = user
    service = _service(request, db)
    rows = await service.list_models(published_only=False)
    settings = request.app.state.settings
    return success(
        request,
        {
            "models": rows,
            "default_input_price": format_money(settings.default_model_input_price),
            "default_output_price": format_money(settings.default_model_output_price),
        },
    )


@router.post("/models/unpublish-batch")
async def unpublish_models_batch(
    body: UnpublishBatchBody,
    request: Request,
    user: User = Depends(require_permission("model:publish")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).unpublish_batch(user.id, body.model_ids)
    return success(request, data)


@router.post("/models/{model_id}/publish")
async def publish_model(
    model_id: UUID,
    body: PublishBody,
    request: Request,
    user: User = Depends(require_permission("model:publish")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).publish(
        user.id,
        model_id,
        display_name=body.display_name,
        supports_stream=body.supports_stream,
        supports_embeddings=body.supports_embeddings,
    )
    return success(request, data)


@router.post("/models/publish-batch")
async def publish_models_batch(
    body: PublishBatchBody,
    request: Request,
    user: User = Depends(require_permission("model:publish")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).publish_batch(
        user.id,
        body.model_ids,
        supports_stream=body.supports_stream,
        supports_embeddings=body.supports_embeddings,
    )
    return success(request, data)


@router.post("/providers/{provider_id}/probe")
async def probe_provider(
    provider_id: UUID,
    body: ProbeBody,
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    _ = user
    data = await _service(request, db).probe(provider_id, body.mode)
    return success(request, data)


@router.get("/deployments")
async def list_deployments(
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    _ = user
    return success(request, await _service(request, db).list_deployments())


@router.post("/deployments/status-batch")
async def deployments_status_batch(
    body: DeploymentStatusBatchBody,
    request: Request,
    user: User = Depends(require_permission("model:publish")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).set_deployments_status_batch(
        user.id,
        body.deployment_ids,
        body.status,
    )
    return success(request, data)


@router.post("/deployments/{deployment_id}/status")
async def deployment_status(
    deployment_id: UUID,
    body: DeploymentStatusBody,
    request: Request,
    user: User = Depends(require_permission("model:publish")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).set_deployment_status(user.id, deployment_id, body.status)
    return success(request, data)
