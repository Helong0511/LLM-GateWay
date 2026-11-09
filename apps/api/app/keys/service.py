"""签发、列出、吊销 API Key，并写入调用记录的两阶段状态。"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import append_audit
from app.auth.passwords import verify_password
from app.auth.tokens import as_utc, digest
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.auth import User
from app.db.models.keys import ApiKey, UsageRecord
from app.keys.cache import KeyCache
from app.keys.crypto import KeyDecryptionError, decrypt, encrypt, is_configured
from app.keys.entitlements import effective_allowed_models


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(value)), "f")


def _loads(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str)]


class KeyService:
    def __init__(self, session: AsyncSession, clock: Clock, cache: KeyCache, settings: Settings | None = None) -> None:
        self.session = session
        self.clock = clock
        self.cache = cache
        self.settings = settings

    def _master_key(self) -> str | None:
        """读取加密主密钥；未配置返回 None（只影响“复制”能力，鉴权不受影响）。"""
        if self.settings is None:
            return None
        return self.settings.encryption_master_key or None

    async def create(
        self,
        user_id: UUID,
        name: str,
        *,
        expires_at: datetime | None = None,
        rpm_limit: int | None = None,
        tpm_limit: int | None = None,
        max_concurrency: int | None = None,
        budget_limit: Decimal | None = None,
        ip_allowlist: list[str] | None = None,
    ) -> dict[str, object]:
        cleaned = name.strip()
        if not cleaned or len(cleaned) > 128:
            raise AppError(400, "KEY_NAME_INVALID")
        secret = "sk-" + secrets.token_urlsafe(32)
        now = self.clock.now()
        ciphertext: str | None = None
        enc_version = 0
        master = self._master_key()
        if master is not None and is_configured(master):
            try:
                ciphertext = encrypt(secret, master)
                enc_version = 1
            except KeyDecryptionError:
                ciphertext = None
                enc_version = 0
        row = ApiKey(
            user_id=user_id,
            name=cleaned,
            key_prefix=secret[:12],
            key_hash=digest(secret),
            key_ciphertext=ciphertext,
            key_enc_version=enc_version,
            status="active",
            expires_at=expires_at,
            rpm_limit=rpm_limit,
            tpm_limit=tpm_limit,
            max_concurrency=max_concurrency,
            budget_limit=budget_limit,
            budget_spent=Decimal("0"),
            allowed_models="[]",
            ip_allowlist=json.dumps(ip_allowlist or []),
            created_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        data = self._public(row)
        data["secret"] = secret
        return data

    async def list_for_user(self, user_id: UUID, *, page: int = 1, page_size: int = 20) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        total = int(
            await self.session.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user_id)) or 0
        )
        result = await self.session.execute(
            select(ApiKey)
            .where(ApiKey.user_id == user_id)
            .order_by(ApiKey.created_at.desc(), ApiKey.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        effective = await effective_allowed_models(self.session, user_id)
        models = sorted(effective) if effective is not None else None
        keys = []
        for row in result.scalars().all():
            item = self._public(row)
            item["effective_models"] = models
            keys.append(item)
        return {**page_meta(page, page_size, total), "keys": keys}

    async def revoke(self, user_id: UUID, key_id: UUID) -> dict[str, object]:
        row = await self._owned(user_id, key_id)
        now = self.clock.now()
        if row.revoked_at is None:
            row.status = "revoked"
            row.revoked_at = now
        await self.cache.delete(row.key_hash)
        return self._public(row)

    async def list_admin(
        self, *, page: int = 1, page_size: int = 20, q: str | None = None, status: str | None = None
    ) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        filters = []
        needle = (q or "").strip().lower()
        if needle:
            filters.append(User.email_normalized.contains(needle))
        if status:
            if status not in {"active", "disabled", "revoked", "expired"}:
                raise AppError(400, "KEY_STATUS_INVALID")
            filters.append(ApiKey.status == status)
        total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(ApiKey)
                .join(User, User.id == ApiKey.user_id)
                .where(*filters)
            )
            or 0
        )
        result = await self.session.execute(
            select(ApiKey, User.email)
            .join(User, User.id == ApiKey.user_id)
            .where(*filters)
            .order_by(ApiKey.created_at.desc(), ApiKey.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        keys = []
        effective_by_user: dict[UUID, list[str] | None] = {}
        for row, email in result.all():
            if row.user_id not in effective_by_user:
                allowed = await effective_allowed_models(self.session, row.user_id)
                effective_by_user[row.user_id] = sorted(allowed) if allowed is not None else None
            item = self._public(row)
            item["email"] = email
            item["effective_models"] = effective_by_user[row.user_id]
            keys.append(item)
        return {**page_meta(page, page_size, total), "keys": keys}

    async def admin_revoke(self, actor_id: UUID, key_id: UUID) -> dict[str, object]:
        row = await self.session.get(ApiKey, key_id)
        if row is None:
            raise AppError(404, "KEY_NOT_FOUND")
        if row.revoked_at is None:
            row.status = "revoked"
            row.revoked_at = self.clock.now()
        await self.cache.delete(row.key_hash)
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="key.revoke",
            target_type="api_key",
            target_id=str(row.id),
            detail=row.key_prefix,
            now=self.clock.now(),
        )
        data = self._public(row)
        data["user_id"] = str(row.user_id)
        return data

    async def admin_limits(
        self,
        actor_id: UUID,
        key_id: UUID,
        *,
        rpm_limit: int | None,
        tpm_limit: int | None,
        max_concurrency: int | None,
        budget_limit: Decimal | None,
    ) -> dict[str, object]:
        row = await self.session.get(ApiKey, key_id)
        if row is None:
            raise AppError(404, "KEY_NOT_FOUND")
        row.rpm_limit = rpm_limit
        row.tpm_limit = tpm_limit
        row.max_concurrency = max_concurrency
        row.budget_limit = budget_limit
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="key.limits",
            target_type="api_key",
            target_id=str(row.id),
            detail=(f"rpm={rpm_limit};tpm={tpm_limit};concurrency={max_concurrency}"),
            now=self.clock.now(),
        )
        return self._public(row)

    async def lookup(self, raw_key: str, *, ip: str | None = None) -> ApiKey:
        if not raw_key.startswith("sk-"):
            raise AppError(401, "API_KEY_BAD_FORMAT")
        key_hash = digest(raw_key)
        cached = await self.cache.get(key_hash)
        if cached == "revoked":
            raise AppError(401, "API_KEY_INVALID")
        result = await self.session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        row = result.scalar_one_or_none()
        if row is None:
            await self.cache.set(key_hash, "revoked")
            raise AppError(401, "API_KEY_MISSING")
        if row.revoked_at is not None or row.status == "revoked":
            await self.cache.set(key_hash, "revoked")
            raise AppError(401, "API_KEY_REVOKED")
        if row.status == "expired":
            await self.cache.set(key_hash, "revoked")
            raise AppError(401, "API_KEY_EXPIRED")
        if row.status == "disabled":
            raise AppError(403, "API_KEY_DISABLED")
        if row.status != "active":
            await self.cache.set(key_hash, "revoked")
            raise AppError(401, "API_KEY_STATUS_INVALID", details={"status": row.status})
        now = self.clock.now()
        if row.expires_at is not None and as_utc(row.expires_at) <= now:
            row.status = "expired"
            await self.cache.set(key_hash, "revoked")
            raise AppError(401, "API_KEY_EXPIRED")
        allowlist = _loads(row.ip_allowlist)
        if allowlist and (not ip or ip not in allowlist):
            raise AppError(403, "API_KEY_IP_DENIED")
        if row.budget_limit is not None and row.budget_spent >= row.budget_limit:
            raise AppError(402, "API_KEY_BUDGET_EXCEEDED")
        row.last_used_at = now
        await self.cache.set(key_hash, "active")
        return row

    async def authenticate(self, raw_key: str, *, model: str | None = None, ip: str | None = None) -> ApiKey:
        row = await self.lookup(raw_key, ip=ip)
        # 模型范围由账号决定（用户级 > 套餐级 > 不限），API Key 不再单独配置。
        allowed = await effective_allowed_models(self.session, row.user_id)
        if model is None or (allowed is not None and model not in allowed):
            raise AppError(403, "API_KEY_MODEL_DENIED")
        return row

    async def start_usage(self, user_id: UUID, api_key_id: UUID | None, request_id: str, model_id: str | None) -> UsageRecord:
        row = UsageRecord(
            request_id=request_id,
            user_id=user_id,
            api_key_id=api_key_id,
            model_id=model_id,
            started_at=self.clock.now(),
            input_tokens=0,
            output_tokens=0,
            cached_tokens=0,
            currency="USD",
            is_stream=False,
            settlement_status="pending",
            created_at=self.clock.now(),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def finalize_usage(
        self,
        request_id: str,
        *,
        input_tokens: int,
        output_tokens: int,
        http_status: int,
        finish_reason: str,
        latency_ms: int | None = None,
        first_token_ms: int | None = None,
        usage_source: str = "reported",
        settlement_status: str = "settled",
        user_charge: Decimal | None = None,
        pricing_version_id: UUID | None = None,
        unit_price_snapshot: str | None = None,
        provider_cost: Decimal | None = None,
        cached_tokens: int = 0,
    ) -> UsageRecord:
        result = await self.session.execute(select(UsageRecord).where(UsageRecord.request_id == request_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(404, "USAGE_NOT_FOUND")
        row.ended_at = self.clock.now()
        row.input_tokens = input_tokens
        row.output_tokens = output_tokens
        row.cached_tokens = cached_tokens
        row.http_status = http_status
        row.latency_ms = latency_ms
        row.first_token_ms = first_token_ms
        row.finish_reason = finish_reason
        row.settlement_status = settlement_status
        row.usage_source = usage_source
        if user_charge is not None:
            row.user_charge = user_charge
        if pricing_version_id is not None:
            row.pricing_version_id = pricing_version_id
        if unit_price_snapshot is not None:
            row.unit_price_snapshot = unit_price_snapshot
        if provider_cost is not None:
            row.provider_cost = provider_cost
        return row

    async def summary(self, user_id: UUID, *, currency: str) -> dict[str, object]:
        now = self.clock.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month = start.replace(day=1)
        today = await self._totals(user_id, start)
        month_rows = await self._totals(user_id, month)
        from app.billing.ledger import LedgerService
        from app.billing.money import format_money

        snap = await LedgerService(self.session, self.clock).snapshot(user_id, currency)
        return {
            "timezone": "UTC",
            "scope": "settled",
            "balance": format_money(snap.available),
            "currency": snap.currency,
            "balance_note": "available_balance",
            "today_requests": today["requests"],
            "today_tokens": today["tokens"],
            "today_charge": await self._charge(user_id, start),
            "month_requests": month_rows["requests"],
            "month_charge": await self._charge(user_id, month),
            "success_rate": today["success_rate"],
            "avg_latency_ms": today["avg_latency_ms"],
            "trend": await self._trend(user_id, now - timedelta(days=14)),
        }

    async def _charge(self, user_id: UUID, start: datetime) -> str | None:
        from app.billing.money import format_money

        result = await self.session.execute(
            select(func.sum(UsageRecord.user_charge)).where(
                UsageRecord.user_id == user_id,
                UsageRecord.started_at >= start,
                UsageRecord.settlement_status == "settled",
            )
        )
        value = result.scalar_one()
        if value is None:
            return None
        return format_money(Decimal(str(value)))

    async def _totals(self, user_id: UUID, start: datetime) -> dict[str, object]:
        result = await self.session.execute(
            select(
                func.count(UsageRecord.id),
                func.coalesce(func.sum(UsageRecord.input_tokens + UsageRecord.output_tokens), 0),
                func.coalesce(func.sum(case((UsageRecord.http_status.between(200, 299), 1), else_=0)), 0),
                func.avg(UsageRecord.latency_ms),
            ).where(
                UsageRecord.user_id == user_id,
                UsageRecord.started_at >= start,
                UsageRecord.settlement_status == "settled",
            )
        )
        requests, tokens, successes, latency = result.one()
        request_count = int(requests or 0)
        rate = None if request_count == 0 else f"{(int(successes) / request_count):.4f}"
        avg_latency = None if latency is None else int(round(float(latency)))
        return {
            "requests": request_count,
            "tokens": int(tokens or 0),
            "success_rate": rate,
            "avg_latency_ms": avg_latency,
        }

    async def list_usage(
        self,
        user_id: UUID,
        *,
        page: int,
        page_size: int,
        model_id: str | None,
        settlement_status: str | None,
        sort: str,
    ) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        filters = [UsageRecord.user_id == user_id]
        if model_id:
            filters.append(UsageRecord.model_id == model_id)
        if settlement_status:
            filters.append(UsageRecord.settlement_status == settlement_status)
        total_result = await self.session.execute(select(func.count()).select_from(UsageRecord).where(*filters))
        total = int(total_result.scalar_one())
        primary = UsageRecord.started_at.asc() if sort == "started_at" else UsageRecord.started_at.desc()
        tie = UsageRecord.id.asc() if sort == "started_at" else UsageRecord.id.desc()
        rows = await self.session.execute(
            select(UsageRecord)
            .where(*filters)
            .order_by(primary, tie)
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        return {
            **page_meta(page, page_size, total),
            "records": [self._usage_public(row) for row in rows.scalars().all()],
        }

    async def _trend(self, user_id: UUID, start: datetime) -> list[dict[str, object]]:
        result = await self.session.execute(
            select(UsageRecord.started_at, UsageRecord.input_tokens, UsageRecord.output_tokens).where(
                UsageRecord.user_id == user_id,
                UsageRecord.started_at >= start,
                UsageRecord.settlement_status == "settled",
            )
        )
        buckets: dict[str, dict[str, int]] = {}
        for started_at, input_tokens, output_tokens in result.all():
            day = as_utc(started_at).date().isoformat()
            bucket = buckets.setdefault(day, {"requests": 0, "tokens": 0})
            bucket["requests"] += 1
            bucket["tokens"] += int(input_tokens or 0) + int(output_tokens or 0)
        return [{"day": day, "requests": buckets[day]["requests"], "tokens": buckets[day]["tokens"]} for day in sorted(buckets)]

    @staticmethod
    def _usage_public(row: UsageRecord) -> dict[str, object]:
        return {
            "id": str(row.id),
            "request_id": row.request_id,
            "model_id": row.model_id,
            "started_at": as_utc(row.started_at).isoformat(),
            "ended_at": as_utc(row.ended_at).isoformat() if row.ended_at else None,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "http_status": row.http_status,
            "latency_ms": row.latency_ms,
            "user_charge": _money(row.user_charge),
            "currency": row.currency,
            "settlement_status": row.settlement_status,
            "finish_reason": row.finish_reason,
        }

    async def _owned(self, user_id: UUID, key_id: UUID) -> ApiKey:
        row = await self.session.get(ApiKey, key_id)
        if row is None or row.user_id != user_id:
            raise AppError(404, "KEY_NOT_FOUND")
        return row

    async def reveal(self, user: User, key_id: UUID, *, password: str, ip: str | None) -> dict[str, object]:
        """经过二次密码验证后解密并返回明文；解密成功和失败都写入审计。"""
        now = self.clock.now()
        row = await self._owned(user.id, key_id)
        ok = False
        detail = f"key={row.key_prefix}"
        try:
            if row.status == "revoked" or row.revoked_at is not None:
                raise AppError(410, "KEY_REVOKED")
            if not verify_password(password, user.password_hash):
                raise AppError(401, "AUTH_BAD_CURRENT_PASSWORD")
            if not row.key_ciphertext or row.key_enc_version == 0:
                # 历史存量密钥（仅存 digest），无法再找回明文。
                raise AppError(410, "KEY_NOT_REVEALABLE")
            master = self._master_key()
            if master is None or not is_configured(master):
                raise AppError(503, "ENCRYPTION_UNCONFIGURED")
            plaintext = decrypt(row.key_ciphertext, master)
            ok = True
            detail += f";ip={ip or '-'};ok=1"
            return {
                "id": str(row.id),
                "name": row.name,
                "secret": plaintext,
                "masked_secret": KeyService.mask_secret(row.key_prefix, plaintext),
            }
        except AppError:
            detail += f";ip={ip or '-'};ok=0"
            raise
        except KeyDecryptionError as exc:
            detail += f";ip={ip or '-'};ok=0"
            raise AppError(500, "KEY_DECRYPT_FAILED", str(exc)) from exc
        finally:
            await append_audit(
                self.session,
                actor_id=user.id,
                action="key.reveal.ok" if ok else "key.reveal.fail",
                target_type="api_key",
                target_id=str(row.id),
                detail=detail[:256],
                now=now,
            )

    @staticmethod
    def mask_secret(prefix: str | None, full: str | None = None) -> str:
        """生成只展示前 8~12 位的掩码，例如 ``sk-abc123***************``。"""
        base = prefix or (full[:12] if full else "")
        if not base:
            return ""
        return base + "*" * max(16, 32 - len(base))

    @staticmethod
    def _public(row: ApiKey) -> dict[str, object]:
        return {
            "id": str(row.id),
            "name": row.name,
            "key_prefix": row.key_prefix,
            "masked_secret": KeyService.mask_secret(row.key_prefix),
            "revealable": bool(row.key_ciphertext and row.key_enc_version > 0),
            "status": row.status,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "rpm_limit": row.rpm_limit,
            "tpm_limit": row.tpm_limit,
            "max_concurrency": row.max_concurrency,
            "budget_limit": _money(row.budget_limit),
            "budget_spent": _money(row.budget_spent),
            "allowed_models": _loads(row.allowed_models),
            "ip_allowlist": _loads(row.ip_allowlist),
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            "created_at": as_utc(row.created_at).isoformat() if row.created_at else None,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        }
