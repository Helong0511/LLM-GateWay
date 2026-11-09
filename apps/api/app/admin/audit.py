"""审计哈希链。只追加，删除不向任何业务角色开放。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.providers import AuditChainLock, AuditEvent

GENESIS = "0" * 64


def recorded_stamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def event_hash(
    *,
    seq: int,
    prev_hash: str,
    actor_id: UUID | None,
    action: str,
    target_type: str,
    target_id: str,
    detail: str,
    recorded_at: str,
) -> str:
    actor = "" if actor_id is None else str(actor_id)
    payload = "\n".join([str(seq), prev_hash, actor, action, target_type, target_id, detail, recorded_at])
    return hashlib.sha256(payload.encode()).hexdigest()


async def append_audit(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    action: str,
    target_type: str,
    target_id: str,
    detail: str,
    now: datetime,
) -> AuditEvent:
    action = action[:64]
    target_type = target_type[:64]
    target_id = target_id[:64]
    detail = detail[:256]
    lock = await session.get(AuditChainLock, 1, with_for_update=True)
    if lock is None:
        session.add(AuditChainLock(id=1))
        await session.flush()
    previous = await session.scalar(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1))
    prev_hash = GENESIS if previous is None else previous.content_hash
    seq = 1 if previous is None else previous.seq + 1
    stamp = recorded_stamp(now)
    digest = event_hash(
        seq=seq,
        prev_hash=prev_hash,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        recorded_at=stamp,
    )
    row = AuditEvent(
        seq=seq,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        prev_hash=prev_hash,
        content_hash=digest,
        recorded_at=stamp,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def verify_chain(session: AsyncSession) -> dict[str, object]:
    rows = list(await session.scalars(select(AuditEvent).order_by(AuditEvent.seq)))
    expected_prev = GENESIS
    expected_seq = 1
    for row in rows:
        digest = event_hash(
            seq=row.seq,
            prev_hash=row.prev_hash,
            actor_id=row.actor_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            detail=row.detail,
            recorded_at=row.recorded_at,
        )
        if row.seq != expected_seq or row.prev_hash != expected_prev or row.content_hash != digest:
            return {"ok": False, "checked": expected_seq - 1, "broken_seq": row.seq}
        expected_prev = row.content_hash
        expected_seq += 1
    return {"ok": True, "checked": len(rows), "broken_seq": None}


async def list_events(session: AsyncSession, *, page: int, page_size: int) -> dict[str, object]:
    from app.core.paging import clamp_page, page_meta, page_offset

    page, page_size = clamp_page(page, page_size)
    total = int(await session.scalar(select(func.count()).select_from(AuditEvent)) or 0)
    result = await session.scalars(
        select(AuditEvent).order_by(AuditEvent.seq.desc()).offset(page_offset(page, page_size)).limit(page_size)
    )
    return {
        **page_meta(page, page_size, total),
        "events": [
            {
                "seq": row.seq,
                "actor_id": None if row.actor_id is None else str(row.actor_id),
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "detail": row.detail,
                "recorded_at": row.recorded_at,
            }
            for row in result.all()
        ],
    }
