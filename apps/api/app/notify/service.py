"""站内通知。安全类通知不能关闭。余额低于预警线时发一条余额通知。"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import as_utc
from app.core.clock import Clock
from app.core.errors import AppError
from app.db.models.keys import ApiKey
from app.db.models.notify import Notification, NotificationPreference

LEDGER_ENABLED = True


class NotifyService:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock

    async def list_for_user(self, user_id: UUID, *, page: int, page_size: int) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        total_result = await self.session.execute(
            select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
        )
        rows = await self.session.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        unread = await self.session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        return {
            **page_meta(page, page_size, int(total_result.scalar_one())),
            "unread": int(unread.scalar_one()),
            "notifications": [self._public(row) for row in rows.scalars().all()],
        }

    async def mark_read(self, user_id: UUID, notification_id: UUID) -> dict[str, object]:
        row = await self.session.get(Notification, notification_id)
        if row is None or row.user_id != user_id:
            raise AppError(404, "NOTIFICATION_NOT_FOUND")
        if row.read_at is None:
            row.read_at = self.clock.now()
        return self._public(row)

    async def preference(self, user_id: UUID) -> dict[str, object]:
        row = await self._preference(user_id)
        return self._preference_public(row)

    async def update_preference(
        self,
        user_id: UUID,
        *,
        enabled: bool,
        warn_high: Decimal,
        warn_low: Decimal,
    ) -> dict[str, object]:
        if warn_high < 0 or warn_low < 0 or warn_high < warn_low:
            raise AppError(400, "BALANCE_ALERT_THRESHOLD_INVALID")
        row = await self._preference(user_id)
        row.balance_alerts_enabled = enabled
        row.warn_high = warn_high
        row.warn_low = warn_low
        row.updated_at = self.clock.now()
        return self._preference_public(row)

    async def key_revoked(self, user_id: UUID, key_id: UUID, name: str) -> None:
        await self._add(
            user_id,
            kind="security",
            title="key_revoked",
            body=name,
            related_id=key_id,
            dedupe_key=f"revoke:{key_id}",
        )

    async def refresh(self, user_id: UUID, *, currency: str) -> dict[str, object]:
        from app.billing.ledger import LedgerService
        from app.billing.money import format_money

        created = await self._scan_expiring_keys(user_id)
        preference = await self._preference(user_id)
        alerts = 0
        reason = ""
        if not preference.balance_alerts_enabled:
            reason = "alerts_disabled"
        else:
            snap = await LedgerService(self.session, self.clock).snapshot(user_id, currency)
            if snap.available <= preference.warn_low or snap.available <= preference.warn_high:
                added = await self._add(
                    user_id,
                    kind="balance",
                    title="balance_low",
                    body=f"{format_money(snap.available)}|{snap.currency}",
                    related_id=None,
                    dedupe_key="balance:low",
                )
                alerts = int(added)
                reason = "checked"
            else:
                reason = "above_threshold"
        return {
            "expiry_notifications": created,
            "balance_alerts": alerts,
            "balance_reason": reason,
            "balance_alerts_enabled": preference.balance_alerts_enabled,
            "warn_high": format(Decimal(str(preference.warn_high)), "f"),
            "warn_low": format(Decimal(str(preference.warn_low)), "f"),
            "ledger_enabled": LEDGER_ENABLED,
        }

    async def _scan_expiring_keys(self, user_id: UUID) -> int:
        now = self.clock.now()
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.status == "active", ApiKey.expires_at.is_not(None))
        )
        created = 0
        for row in result.scalars().all():
            if row.expires_at is None:
                continue
            remaining = as_utc(row.expires_at) - now
            if remaining <= timedelta(0) or remaining > timedelta(days=7):
                continue
            window = "1d" if remaining <= timedelta(days=1) else "7d"
            added = await self._add(
                user_id,
                kind="key_expiry",
                title="key_expiry_7d" if window == "7d" else "key_expiry_1d",
                body=f"{row.name}|{as_utc(row.expires_at).isoformat()}",
                related_id=row.id,
                dedupe_key=f"expiry:{window}:{row.id}",
            )
            created += int(added)
        return created

    async def _preference(self, user_id: UUID) -> NotificationPreference:
        row = await self.session.get(NotificationPreference, user_id)
        if row is not None:
            return row
        row = NotificationPreference(
            user_id=user_id,
            balance_alerts_enabled=True,
            warn_high=Decimal("10"),
            warn_low=Decimal("2"),
            updated_at=self.clock.now(),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def _add(
        self,
        user_id: UUID,
        *,
        kind: str,
        title: str,
        body: str,
        related_id: UUID | None,
        dedupe_key: str,
    ) -> bool:
        existing = await self.session.execute(
            select(Notification).where(Notification.user_id == user_id, Notification.dedupe_key == dedupe_key)
        )
        if existing.scalar_one_or_none() is not None:
            return False
        self.session.add(
            Notification(
                user_id=user_id,
                kind=kind,
                title=title,
                body=body,
                related_id=related_id,
                dedupe_key=dedupe_key,
                created_at=self.clock.now(),
            )
        )
        await self.session.flush()
        return True

    @staticmethod
    def _preference_public(row: NotificationPreference) -> dict[str, object]:
        return {
            "balance_alerts_enabled": row.balance_alerts_enabled,
            "warn_high": format(row.warn_high, "f"),
            "warn_low": format(row.warn_low, "f"),
        }

    @staticmethod
    def _public(row: Notification) -> dict[str, object]:
        return {
            "id": str(row.id),
            "kind": row.kind,
            "title": row.title,
            "body": row.body,
            "read_at": row.read_at.isoformat() if row.read_at else None,
            "created_at": as_utc(row.created_at).isoformat(),
        }
