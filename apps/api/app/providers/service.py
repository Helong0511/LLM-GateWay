"""供应商、白名单、模型同步与上架。响应里只有密钥掩码。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import append_audit
from app.auth.crypto import decrypt_text, encrypt_text
from app.billing.money import format_money, settlement_currency
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.billing import ModelPrice, PricingVersion
from app.db.models.providers import (
    EndpointAllowlist,
    ModelCatalog,
    ModelDeployment,
    ModelSyncJob,
    ModelTestRun,
    Provider,
    ProviderCredential,
)
from app.providers.presets import (
    auth_headers,
    default_protocol,
    endpoint_paths,
    join_api_url,
    list_presets,
)
from app.providers.upstream_pricing import (
    UpstreamModelQuote,
    classify_price_change,
    parse_upstream_models,
    suggest_prices,
)
from app.security.ssrf import Resolver, fetch_checked, inspect_url
from app.providers.litellm_registry import LiteLLMRegistry, RegistryError

_SYNC_NAME_SAMPLE = 8

TEST_RETENTION = timedelta(days=7)
_KINDS = {"openai", "anthropic", "cloud", "self_hosted", "ollama", "compatible"}

# P1: 进程内 allowlist 缓存 {key: (timestamp, value)}
_allowlist_cache: dict[str, tuple[float, set[str]]] = {}


def secret_hint(secret: str) -> str:
    if len(secret) < 12:
        return "****"
    return f"{secret[:4]}…{secret[-4:]}"


class ProviderService:
    def __init__(
        self,
        session: AsyncSession,
        clock: Clock,
        settings: Settings,
        resolver: Resolver,
        transport: httpx.AsyncBaseTransport | None,
        *,
        upstream_client: httpx.AsyncClient | None = None,
        registry: LiteLLMRegistry | None = None,
    ) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings
        self.resolver = resolver
        self.transport = transport
        self.client = upstream_client  # 全局持久化 httpx.AsyncClient（连接池复用）
        self.registry = registry if registry is not None else LiteLLMRegistry(settings)

    @asynccontextmanager
    async def _http(self, timeout: float) -> AsyncIterator[httpx.AsyncClient]:
        """按优先级返回上游客户端。

        transport（测试/私有链路注入）必须高于 upstream_client，否则注入被全局
        客户端覆盖，请求会真的外连——与网关侧 P1-1 同类缺陷。
        """
        if self.transport is not None:
            async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as client:
                yield client
            return
        if self.client is not None:
            existing = self.client.timeout
            self.client.timeout = httpx.Timeout(timeout)
            try:
                yield self.client
            finally:
                self.client.timeout = existing
            return
        async with httpx.AsyncClient(timeout=timeout) as client:
            yield client

    async def create(self, actor_id: UUID, name: str, kind: str, base_url: str) -> dict[str, object]:
        if kind not in _KINDS:
            raise AppError(400, "PROVIDER_TYPE_INVALID")
        cleaned = name.strip()
        if not cleaned:
            raise AppError(400, "PROVIDER_NAME_EMPTY")
        root = base_url.strip().rstrip("/")
        allowlist = await self._allowlist()
        await inspect_url(root, resolver=self.resolver, allowlist=allowlist, endpoint_kind=kind)
        now = self.clock.now()
        row = Provider(
            name=cleaned,
            kind=kind,
            base_url=root,
            protocol=default_protocol(kind),
            status="active",
            timeout_seconds=60,
            priority=100,
            weight=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(actor_id, "provider.create", "provider", str(row.id), cleaned)
        return self._public_provider(row, [])

    @staticmethod
    def presets() -> list[dict[str, object]]:
        return list_presets()

    async def list_providers(self) -> list[dict[str, object]]:
        result = await self.session.execute(select(Provider).order_by(Provider.created_at.desc()))
        rows = list(result.scalars().all())
        output: list[dict[str, object]] = []
        for row in rows:
            credentials = await self.session.execute(
                select(ProviderCredential).where(ProviderCredential.provider_id == row.id)
            )
            output.append(self._public_provider(row, list(credentials.scalars().all())))
        return output

    async def add_credential(self, actor_id: UUID, provider_id: UUID, label: str, secret: str) -> dict[str, object]:
        provider = await self._provider(provider_id)
        if not secret or len(secret) > 4096:
            raise AppError(400, "PROVIDER_CREDENTIAL_EMPTY")
        now = self.clock.now()
        existing = await self.session.execute(
            select(ProviderCredential).where(
                ProviderCredential.provider_id == provider.id,
                ProviderCredential.status == "active",
            )
        )
        for row in existing.scalars().all():
            row.status = "revoked"
        created = ProviderCredential(
            provider_id=provider.id,
            label=label.strip() or "default",
            secret_ciphertext=encrypt_text(self.settings.encryption_master_key, secret),
            secret_hint=secret_hint(secret),
            status="active",
            created_at=now,
        )
        self.session.add(created)
        await self.session.flush()
        await self._audit(actor_id, "credential.rotate", "provider", str(provider.id), created.secret_hint)
        return {"id": str(created.id), "label": created.label, "hint": created.secret_hint, "status": created.status}

    async def approve_host(self, actor_id: UUID, host: str, note: str) -> dict[str, object]:
        cleaned = host.strip().lower().rstrip(".")
        if not cleaned or "/" in cleaned:
            raise AppError(400, "PROVIDER_ALLOWLIST_HOST_INVALID")
        result = await self.session.execute(select(EndpointAllowlist).where(EndpointAllowlist.host == cleaned))
        row = result.scalar_one_or_none()
        now = self.clock.now()
        if row is None:
            row = EndpointAllowlist(host=cleaned, approved=True, note=note[:256], created_at=now)
            self.session.add(row)
        else:
            row.approved = True
            row.note = note[:256]
        await self.session.flush()
        # P1: allowlist 变更时立即失效缓存
        _allowlist_cache.pop("allowlist", None)
        await self._audit(actor_id, "allowlist.approve", "endpoint", cleaned, "自建端点已批准")
        return {"id": str(row.id), "host": row.host, "approved": row.approved}

    async def sync_models(
        self,
        actor_id: UUID,
        provider_id: UUID,
        *,
        output_markup_percent: float = 10,
    ) -> dict[str, object]:
        provider = await self._provider(provider_id)
        secret = await self._secret(provider.id)
        now = self.clock.now()
        job = ModelSyncJob(provider_id=provider.id, status="running", discovered_count=0, started_at=now)
        self.session.add(job)
        await self.session.flush()
        try:
            quotes = await self._upstream_models(provider, secret)
        except AppError as exc:
            job.status = "failed"
            job.error = exc.message[:256]
            job.finished_at = self.clock.now()
            provider.last_error = exc.message[:256]
            raise
        markup = Decimal(str(output_markup_percent))
        priced = 0
        price_new = 0
        price_unchanged = 0
        price_defaulted = 0
        price_increased: list[str] = []
        price_decreased: list[str] = []
        price_mixed: list[str] = []
        touched_ids: list[UUID] = []
        suggested_by_id: dict[UUID, UpstreamModelQuote] = {}
        for quote in quotes:
            adjusted, used_default = suggest_prices(
                quote,
                default_input=self.settings.default_model_input_price,
                markup_percent=markup,
            )
            row, change = await self._upsert_pending(provider.id, adjusted)
            if change is None:
                continue
            priced += 1
            if used_default:
                price_defaulted += 1
            touched_ids.append(row.id)
            suggested_by_id[row.id] = adjusted
            label = row.public_name or row.upstream_name
            if change == "new":
                price_new += 1
            elif change == "unchanged":
                price_unchanged += 1
            elif change == "increased":
                price_increased.append(label)
            elif change == "decreased":
                price_decreased.append(label)
            elif change == "mixed":
                price_mixed.append(label)
        published_below = await self._published_below_suggested(touched_ids, suggested_by_id)
        job.status = "succeeded"
        job.discovered_count = len(quotes)
        job.finished_at = self.clock.now()
        await self._audit(
            actor_id,
            "model.sync",
            "provider",
            str(provider.id),
            (
                f"发现 {len(quotes)} 个模型；写入上游价 {priced}；输出加价 {markup}%；"
                f"涨价 {len(price_increased)}；降价 {len(price_decreased)}；"
                f"生效售价偏低 {len(published_below)}"
            ),
        )
        return {
            "job_id": str(job.id),
            "discovered_count": len(quotes),
            "priced_count": priced,
            "price_new": price_new,
            "price_unchanged": price_unchanged,
            "price_defaulted": price_defaulted,
            "price_increased": len(price_increased),
            "price_decreased": len(price_decreased),
            "price_mixed": len(price_mixed),
            "price_increased_models": price_increased[:_SYNC_NAME_SAMPLE],
            "price_decreased_models": price_decreased[:_SYNC_NAME_SAMPLE],
            "price_mixed_models": price_mixed[:_SYNC_NAME_SAMPLE],
            "published_below_suggested": len(published_below),
            "published_below_models": published_below[:_SYNC_NAME_SAMPLE],
            "default_input_price": format_money(self.settings.default_model_input_price),
            "default_output_price": format_money(self.settings.default_model_output_price),
            "output_markup_percent": float(markup),
            "status": "pending",
        }

    async def publish(
        self,
        actor_id: UUID,
        model_id: UUID,
        *,
        display_name: str,
        supports_stream: bool,
        supports_embeddings: bool,
    ) -> dict[str, object]:
        row = await self.session.get(ModelCatalog, model_id)
        if row is None:
            raise AppError(404, "PROVIDER_MODEL_NOT_FOUND")
        # 已上架模型再次提交只是编辑设置，不能顺带改动部署状态；
        # 待上架/已下架模型重新上架时必须恢复部署为 active，否则网关会判定不可调用。
        was_published = row.status == "published"
        row.display_name = display_name.strip() or row.upstream_name
        row.supports_stream = supports_stream
        row.supports_embeddings = supports_embeddings
        row.status = "published"
        existing = await self.session.execute(select(ModelDeployment).where(ModelDeployment.model_id == row.id))
        deployment = existing.scalar_one_or_none()
        if deployment is None:
            self.session.add(
                ModelDeployment(
                    model_id=row.id,
                    provider_id=row.provider_id,
                    status="active",
                    created_at=self.clock.now(),
                )
            )
        elif not was_published:
            deployment.status = "active"
        await self._audit(actor_id, "model.publish", "model", str(row.id), row.public_name)
        return self._public_model(row)

    async def publish_batch(
        self,
        actor_id: UUID,
        model_ids: list[UUID],
        *,
        supports_stream: bool = True,
        supports_embeddings: bool = False,
    ) -> dict[str, object]:
        """批量上架待确认模型；已上架的跳过。用现有显示名，缺省时用上游名。"""
        if not model_ids:
            raise AppError(400, "VALIDATION_ERROR")
        # 去重且保序，避免同一请求重复写部署
        seen: set[UUID] = set()
        ordered: list[UUID] = []
        for model_id in model_ids:
            if model_id in seen:
                continue
            seen.add(model_id)
            ordered.append(model_id)
        if len(ordered) > 500:
            raise AppError(400, "VALIDATION_ERROR")
        published = 0
        skipped = 0
        missing = 0
        for model_id in ordered:
            row = await self.session.get(ModelCatalog, model_id)
            if row is None:
                missing += 1
                continue
            if row.status == "published":
                skipped += 1
                continue
            await self.publish(
                actor_id,
                model_id,
                display_name=row.display_name or row.upstream_name,
                # 已下架模型保留原有能力设置；仅待上架（能力未知）用批量默认值。
                supports_stream=supports_stream if row.supports_stream is None else row.supports_stream,
                supports_embeddings=(
                    supports_embeddings if row.supports_embeddings is None else row.supports_embeddings
                ),
            )
            published += 1
        await self._audit(
            actor_id,
            "model.publish_batch",
            "model",
            "",
            f"published={published};skipped={skipped};missing={missing}",
        )
        return {"published": published, "skipped": skipped, "missing": missing, "requested": len(ordered)}

    async def unpublish_batch(self, actor_id: UUID, model_ids: list[UUID]) -> dict[str, object]:
        """批量下架已上架模型；待上架/已下架跳过，关联部署一并停用。"""
        if not model_ids:
            raise AppError(400, "VALIDATION_ERROR")
        seen: set[UUID] = set()
        ordered: list[UUID] = []
        for model_id in model_ids:
            if model_id in seen:
                continue
            seen.add(model_id)
            ordered.append(model_id)
        if len(ordered) > 500:
            raise AppError(400, "VALIDATION_ERROR")
        unpublished = 0
        skipped = 0
        missing = 0
        for model_id in ordered:
            row = await self.session.get(ModelCatalog, model_id)
            if row is None:
                missing += 1
                continue
            if row.status != "published":
                skipped += 1
                continue
            row.status = "disabled"
            deployments = await self.session.execute(
                select(ModelDeployment).where(ModelDeployment.model_id == row.id)
            )
            for deployment in deployments.scalars().all():
                deployment.status = "disabled"
            unpublished += 1
        await self.session.flush()
        await self._audit(
            actor_id,
            "model.unpublish_batch",
            "model",
            "",
            f"unpublished={unpublished};skipped={skipped};missing={missing}",
        )
        return {
            "unpublished": unpublished,
            "skipped": skipped,
            "missing": missing,
            "requested": len(ordered),
        }

    async def list_deployments(self) -> dict[str, object]:
        result = await self.session.execute(
            select(
                ModelDeployment,
                ModelCatalog.public_name,
                ModelCatalog.display_name,
                ModelCatalog.status,
                Provider.name,
            )
            .join(ModelCatalog, ModelCatalog.id == ModelDeployment.model_id)
            .join(Provider, Provider.id == ModelDeployment.provider_id)
            .order_by(ModelDeployment.created_at.desc())
        )
        rows = []
        for deployment, public_name, display_name, model_status, provider_name in result.all():
            rows.append(
                {
                    "id": str(deployment.id),
                    "model_id": str(deployment.model_id),
                    "provider_id": str(deployment.provider_id),
                    "public_name": public_name,
                    "display_name": display_name,
                    "provider_name": provider_name,
                    "status": deployment.status,
                    # 网关要求模型 published 且部署 active 才可调用，前端据此禁用无效启用。
                    "model_status": model_status,
                }
            )
        return {"deployments": rows}

    async def set_deployment_status(self, actor_id: UUID, deployment_id: UUID, status: str) -> dict[str, object]:
        if status not in {"active", "disabled"}:
            raise AppError(400, "DEPLOYMENT_STATUS_INVALID")
        row = await self.session.get(ModelDeployment, deployment_id)
        if row is None:
            raise AppError(404, "DEPLOYMENT_NOT_FOUND")
        catalog = await self.session.get(ModelCatalog, row.model_id)
        if status == "active" and (catalog is None or catalog.status != "published"):
            raise AppError(409, "DEPLOYMENT_MODEL_UNPUBLISHED")
        row.status = status
        await self._audit(actor_id, "deployment.status", "deployment", str(row.id), status)
        provider = await self.session.get(Provider, row.provider_id)
        return {
            "id": str(row.id),
            "model_id": str(row.model_id),
            "provider_id": str(row.provider_id),
            "public_name": "" if catalog is None else catalog.public_name,
            "display_name": "" if catalog is None else catalog.display_name,
            "provider_name": "" if provider is None else provider.name,
            "status": row.status,
            "model_status": "" if catalog is None else catalog.status,
        }

    async def set_deployments_status_batch(
        self,
        actor_id: UUID,
        deployment_ids: list[UUID],
        status: str,
    ) -> dict[str, object]:
        if status not in {"active", "disabled"}:
            raise AppError(400, "DEPLOYMENT_STATUS_INVALID")
        if not deployment_ids:
            raise AppError(400, "VALIDATION_ERROR")
        seen: set[UUID] = set()
        ordered: list[UUID] = []
        for item_id in deployment_ids:
            if item_id in seen:
                continue
            seen.add(item_id)
            ordered.append(item_id)
        if len(ordered) > 500:
            raise AppError(400, "VALIDATION_ERROR")
        updated = 0
        skipped = 0
        missing = 0
        blocked = 0
        for item_id in ordered:
            row = await self.session.get(ModelDeployment, item_id)
            if row is None:
                missing += 1
                continue
            if status == "active":
                catalog = await self.session.get(ModelCatalog, row.model_id)
                if catalog is None or catalog.status != "published":
                    blocked += 1
                    continue
            if row.status == status:
                skipped += 1
                continue
            row.status = status
            updated += 1
        await self._audit(
            actor_id,
            "deployment.status_batch",
            "deployment",
            "",
            f"status={status};updated={updated};skipped={skipped};missing={missing};blocked={blocked}",
        )
        return {
            "status": status,
            "updated": updated,
            "skipped": skipped,
            "missing": missing,
            "blocked": blocked,
            "requested": len(ordered),
        }

    async def list_models(self, *, published_only: bool) -> list[dict[str, object]]:
        statement = (
            select(ModelCatalog, Provider.name)
            .join(Provider, Provider.id == ModelCatalog.provider_id)
            .order_by(ModelCatalog.created_at.desc())
        )
        if published_only:
            disabled = select(ModelDeployment.model_id).where(ModelDeployment.status == "disabled")
            statement = statement.where(ModelCatalog.status == "published", ModelCatalog.id.not_in(disabled))
        result = await self.session.execute(statement)
        return [self._public_model(row, provider_name=provider_name) for row, provider_name in result.all()]

    async def probe(self, provider_id: UUID, mode: str) -> dict[str, object]:
        if mode not in {"connect", "generate", "stream", "timeout", "auth", "missing", "usage"}:
            raise AppError(400, "PROVIDER_TEST_TYPE_INVALID")
        # P3: _purge_tests 异步 fire-and-forget（不阻塞主流程）
        loop = asyncio.get_running_loop()
        loop.create_task(self._purge_tests())

        # P2: provider / secret / allowlist 并行查询
        provider, secret, allowlist = await asyncio.gather(
            self._provider(provider_id),
            self._secret(provider_id),
            self._allowlist(),
        )

        started = self.clock.now()
        http_status: int | None = None
        usage_present = False
        error: str | None = None
        ok = False
        try:
            response = await self._probe_request(provider, secret, mode, allowlist)
            http_status = response.status_code
            payload = self._json_or_empty(response)
            usage_present = self._has_usage(payload, response.text)
            ok = self._probe_ok(mode, http_status, usage_present)
            if not ok:
                error = f"HTTP {http_status}"
        except httpx.TimeoutException:
            error = "超时"
        except AppError as exc:
            error = exc.message
        latency = int((self.clock.now() - started).total_seconds() * 1000)
        run = ModelTestRun(
            provider_id=provider.id,
            mode=mode,
            ok=ok,
            http_status=http_status,
            latency_ms=latency,
            usage_present=usage_present,
            error=None if error is None else error[:256],
            created_at=self.clock.now(),
        )
        self.session.add(run)
        await self.session.flush()
        return {
            "id": str(run.id),
            "mode": mode,
            "ok": ok,
            "http_status": http_status,
            "latency_ms": latency,
            "usage_present": usage_present,
            "error": error,
        }

    async def _probe_request(
        self, provider: Provider, secret: str, mode: str, allowlist: set[str] | None = None
    ) -> httpx.Response:
        timeout = 0.01 if mode == "timeout" else provider.timeout_seconds
        models_path, chat_path = endpoint_paths(provider.kind, provider.base_url)
        path = models_path if mode == "connect" else chat_path
        body: dict[str, object] | None = None
        if mode != "connect":
            if provider.kind == "anthropic" or provider.protocol == "anthropic":
                body = {
                    "model": "__missing__" if mode == "missing" else "claude-3-haiku-20240307",
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "ping"}],
                    "stream": mode == "stream",
                }
            else:
                body = {
                    "model": "__missing__" if mode == "missing" else "mock-model",
                    "messages": [{"role": "user", "content": "ping"}],
                    "stream": mode == "stream",
                }
        token = "invalid-token" if mode == "auth" else secret
        # P0: 优先用全局持久化 AsyncClient（连接池复用，省 SSL/TLS 握手时间）
        if allowlist is None:
            allowlist = await self._allowlist()
        headers = auth_headers(provider.kind, provider.base_url, token)
        url = join_api_url(provider.base_url, path)
        async with self._http(timeout) as client:
            response = await fetch_checked(
                client,
                "GET" if mode == "connect" else "POST",
                url,
                resolver=self.resolver,
                allowlist=allowlist,
                endpoint_kind=provider.kind,
                headers=headers,
                json_body=body,
            )
        if not isinstance(response, httpx.Response):
            raise AppError(502, "PROVIDER_UPSTREAM_NO_RESPONSE")
        return response

    async def _upstream_models(self, provider: Provider, secret: str) -> list[UpstreamModelQuote]:
        models_path, _ = endpoint_paths(provider.kind, provider.base_url)
        allowlist = await self._allowlist()
        headers = auth_headers(provider.kind, provider.base_url, secret)
        url = join_api_url(provider.base_url, models_path)
        async with self._http(provider.timeout_seconds) as client:
            response = await fetch_checked(
                client, "GET", url,
                resolver=self.resolver, allowlist=allowlist,
                endpoint_kind=provider.kind, headers=headers,
            )
        if not isinstance(response, httpx.Response) or response.status_code >= 400:
            raise AppError(502, "PROVIDER_MODELS_FETCH_FAILED")
        payload = response.json()
        quotes = parse_upstream_models(payload)
        if not quotes:
            raise AppError(502, "PROVIDER_MODELS_FORMAT_INVALID")
        return quotes

    async def _upsert_pending(
        self, provider_id: UUID, quote: UpstreamModelQuote
    ) -> tuple[ModelCatalog, str | None]:
        """写入/更新目录建议价。返回 (行, 价格变动类别)；无上游价时类别为 None。"""
        result = await self.session.execute(
            select(ModelCatalog).where(
                ModelCatalog.provider_id == provider_id,
                ModelCatalog.upstream_name == quote.upstream_name,
            )
        )
        row = result.scalar_one_or_none()
        has_price = quote.input_price is not None or quote.output_price is not None
        if row is None:
            row = ModelCatalog(
                provider_id=provider_id,
                public_name=quote.upstream_name,
                display_name=quote.upstream_name,
                upstream_name=quote.upstream_name,
                status="pending",
                upstream_input_price=quote.input_price,
                upstream_output_price=quote.output_price,
                created_at=self.clock.now(),
            )
            self.session.add(row)
            await self.session.flush()
            return row, ("new" if has_price else None)

        change = classify_price_change(
            old_input=row.upstream_input_price,
            old_output=row.upstream_output_price,
            new_input=quote.input_price,
            new_output=quote.output_price,
        )
        if quote.input_price is not None:
            row.upstream_input_price = quote.input_price
        if quote.output_price is not None:
            row.upstream_output_price = quote.output_price
        return row, change

    async def _published_below_suggested(
        self,
        model_ids: list[UUID],
        suggested_by_id: dict[UUID, UpstreamModelQuote],
    ) -> list[str]:
        """已发布生效售价低于本次建议价的模型（成本上涨后售价未跟上）。"""
        if not model_ids:
            return []
        currency = settlement_currency(self.settings.operating_mode)
        now = self.clock.now()
        versions = await self.session.execute(
            select(PricingVersion)
            .where(
                PricingVersion.model_id.in_(model_ids),
                PricingVersion.currency == currency,
                PricingVersion.effective_from <= now,
                (PricingVersion.effective_to.is_(None)) | (PricingVersion.effective_to > now),
            )
            .order_by(PricingVersion.model_id.asc(), PricingVersion.version.desc())
        )
        latest: dict[UUID, PricingVersion] = {}
        for version in versions.scalars().all():
            if version.model_id not in latest:
                latest[version.model_id] = version
        if not latest:
            return []
        version_ids = [item.id for item in latest.values()]
        meters = await self.session.execute(
            select(ModelPrice).where(
                ModelPrice.pricing_version_id.in_(version_ids),
                ModelPrice.meter.in_(("input_token", "output_token")),
            )
        )
        by_version: dict[UUID, dict[str, ModelPrice]] = {}
        for price in meters.scalars().all():
            by_version.setdefault(price.pricing_version_id, {})[price.meter] = price
        names: list[str] = []
        id_to_name = {
            row.id: (row.public_name or row.upstream_name)
            for row in (
                await self.session.execute(select(ModelCatalog).where(ModelCatalog.id.in_(list(latest.keys()))))
            ).scalars().all()
        }
        for model_id, version in latest.items():
            suggested = suggested_by_id.get(model_id)
            if suggested is None:
                continue
            published = by_version.get(version.id, {})
            below = False
            input_row = published.get("input_token")
            output_row = published.get("output_token")
            if (
                suggested.input_price is not None
                and input_row is not None
                and suggested.input_price > input_row.unit_price
            ):
                below = True
            if (
                suggested.output_price is not None
                and output_row is not None
                and suggested.output_price > output_row.unit_price
            ):
                below = True
            if below:
                names.append(id_to_name.get(model_id, str(model_id)))
        return names

    async def _secret(self, provider_id: UUID) -> str:
        result = await self.session.execute(
            select(ProviderCredential).where(
                ProviderCredential.provider_id == provider_id,
                ProviderCredential.status == "active",
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(400, "PROVIDER_NO_CREDENTIAL")
        row.last_used_at = self.clock.now()
        return decrypt_text(
            self.settings.encryption_master_key,
            row.secret_ciphertext,
            code="CREDENTIAL_DECRYPT_FAILED",
        )

    async def _allowlist(self) -> set[str]:
        # P1: 进程内 TTL 缓存（allowlist 很少变，60 秒过期）
        _CACHE_TTL = 60.0  # 秒
        now = self.clock.now().timestamp()
        cache_key = "allowlist"
        cached_ts, cached_val = _allowlist_cache.get(cache_key, (0.0, None))
        if cached_val is not None and (now - cached_ts) < _CACHE_TTL:
            return cached_val
        result = await self.session.execute(select(EndpointAllowlist.host).where(EndpointAllowlist.approved.is_(True)))
        val = {str(host) for host in result.scalars().all()}
        _allowlist_cache[cache_key] = (now, val)
        return val

    async def _provider(self, provider_id: UUID) -> Provider:
        row = await self.session.get(Provider, provider_id)
        if row is None:
            raise AppError(404, "PROVIDER_NOT_FOUND")
        return row

    async def _purge_tests(self) -> None:
        cutoff = self.clock.now() - TEST_RETENTION
        await self.session.execute(delete(ModelTestRun).where(ModelTestRun.created_at < cutoff))

    async def _audit(self, actor_id: UUID, action: str, target_type: str, target_id: str, detail: str) -> None:
        await append_audit(
            self.session,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            now=self.clock.now(),
        )

    @staticmethod
    def _public_provider(row: Provider, credentials: list[ProviderCredential]) -> dict[str, object]:
        models_path, chat_path = endpoint_paths(row.kind, row.base_url)
        return {
            "id": str(row.id),
            "name": row.name,
            "kind": row.kind,
            "protocol": row.protocol,
            "base_url": row.base_url,
            "models_url": join_api_url(row.base_url, models_path),
            "chat_url": join_api_url(row.base_url, chat_path),
            "status": row.status,
            "timeout_seconds": row.timeout_seconds,
            "priority": row.priority,
            "weight": row.weight,
            "last_error": row.last_error,
            "last_latency_ms": row.last_latency_ms,
            "credentials": [
                {"id": str(item.id), "label": item.label, "hint": item.secret_hint, "status": item.status}
                for item in credentials
            ],
        }

    @staticmethod
    def _public_model(row: ModelCatalog, *, provider_name: str = "") -> dict[str, object]:
        return {
            "id": str(row.id),
            "provider_id": str(row.provider_id),
            "provider_name": provider_name,
            "public_name": row.public_name,
            "display_name": row.display_name,
            "upstream_name": row.upstream_name,
            "status": row.status,
            "supports_stream": row.supports_stream,
            "supports_tools": row.supports_tools,
            "supports_vision": row.supports_vision,
            "supports_embeddings": row.supports_embeddings,
            "supports_images": row.supports_images,
            "context_window": row.context_window,
            "max_output": row.max_output,
            "upstream_input_price": None
            if row.upstream_input_price is None
            else format_money(row.upstream_input_price),
            "upstream_output_price": None
            if row.upstream_output_price is None
            else format_money(row.upstream_output_price),
        }

    @staticmethod
    def _json_or_empty(response: httpx.Response) -> dict[str, object]:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    @staticmethod
    def _has_usage(payload: dict[str, object], text: str) -> bool:
        usage = payload.get("usage")
        return isinstance(usage, dict) or '"usage"' in text

    @staticmethod
    def _probe_ok(mode: str, status: int, usage_present: bool) -> bool:
        if mode == "auth":
            return status == 401
        if mode == "missing":
            return status == 404
        if mode == "usage":
            return status < 400 and usage_present
        return status < 400
