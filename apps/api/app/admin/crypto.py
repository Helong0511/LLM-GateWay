"""加密资产台账：收款尾数只读；制裁地址可增删改。不接触私钥。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import append_audit
from app.billing.money import format_money
from app.core.clock import Clock
from app.core.errors import AppError
from app.core.paging import clamp_page, page_meta, page_offset
from app.db.models.auth import User
from app.db.models.payments import CryptoDepositIntent, PaymentOrder, SanctionedAddress

SANCTION_NETWORKS = frozenset({"TRC20", "ERC20"})
SOURCE_MAX = 64
REASON_MAX = 256
ADDRESS_MAX = 128


def _mask(value: str) -> str:
    if len(value) < 16:
        return value
    return value[:8] + "…" + value[-8:]


def normalize_network(network: str) -> str:
    cleaned = (network or "").strip().upper()
    if cleaned not in SANCTION_NETWORKS:
        raise AppError(400, "SANCTION_NETWORK_INVALID")
    return cleaned


def normalize_sanction_address(address: str, network: str) -> str:
    cleaned = (address or "").strip()
    if not cleaned:
        raise AppError(400, "SANCTION_ADDRESS_REQUIRED")
    if len(cleaned) > ADDRESS_MAX:
        raise AppError(400, "SANCTION_ADDRESS_TOO_LONG", details={"max": ADDRESS_MAX})
    if network == "ERC20":
        # 以太坊地址大小写不敏感，统一成小写 0x…
        if cleaned.startswith(("0x", "0X")):
            body = cleaned[2:]
        else:
            body = cleaned
        if not body or any(ch not in "0123456789abcdefABCDEF" for ch in body):
            raise AppError(400, "SANCTION_ERC20_HEX")
        if len(body) != 40:
            raise AppError(400, "SANCTION_ERC20_LENGTH")
        return "0x" + body.lower()
    # TRC20：Base58，大小写敏感，只去空白
    if " " in cleaned or "\t" in cleaned:
        raise AppError(400, "SANCTION_TRC20_WHITESPACE")
    if not cleaned.startswith("T"):
        raise AppError(400, "SANCTION_TRC20_PREFIX")
    if len(cleaned) < 26 or len(cleaned) > 64:
        raise AppError(400, "SANCTION_TRC20_LENGTH")
    return cleaned


def _public_sanction(row: SanctionedAddress) -> dict[str, object]:
    return {
        "id": str(row.id),
        "address": row.address,
        "address_masked": _mask(row.address),
        "network": row.network,
        "source": row.source,
        "reason": row.reason,
        "created_at": row.created_at.isoformat(),
    }


async def admin_crypto(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    sanctioned_page: int = 1,
    sanctioned_page_size: int = 20,
    q: str | None = None,
) -> dict[str, object]:
    page, page_size = clamp_page(page, page_size)
    sanctioned_page, sanctioned_page_size = clamp_page(sanctioned_page, sanctioned_page_size)

    total = int(await session.scalar(select(func.count()).select_from(CryptoDepositIntent)) or 0)
    intents = await session.execute(
        select(CryptoDepositIntent, PaymentOrder.order_no, User.email)
        .join(PaymentOrder, PaymentOrder.id == CryptoDepositIntent.order_id)
        .join(User, User.id == PaymentOrder.user_id)
        .order_by(CryptoDepositIntent.expires_at.desc(), CryptoDepositIntent.id.desc())
        .offset(page_offset(page, page_size))
        .limit(page_size)
    )

    filters = []
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        filters.append(
            or_(
                SanctionedAddress.address.ilike(like),
                SanctionedAddress.network.ilike(like),
                SanctionedAddress.source.ilike(like),
                SanctionedAddress.reason.ilike(like),
            )
        )
    blocked_total = int(
        await session.scalar(select(func.count()).select_from(SanctionedAddress).where(*filters)) or 0
    )
    blocked = await session.scalars(
        select(SanctionedAddress)
        .where(*filters)
        .order_by(SanctionedAddress.created_at.desc(), SanctionedAddress.id.desc())
        .offset(page_offset(sanctioned_page, sanctioned_page_size))
        .limit(sanctioned_page_size)
    )
    intents_meta = page_meta(page, page_size, total)
    sanctioned_meta = page_meta(sanctioned_page, sanctioned_page_size, blocked_total)
    return {
        **intents_meta,
        "intents": [
            {
                "order_no": order_no,
                "email": email,
                "address": _mask(intent.address),
                "network": intent.network,
                "tail_amount": format_money(intent.tail_amount),
                "tail_status": intent.tail_status,
                "expires_at": intent.expires_at.isoformat(),
            }
            for intent, order_no, email in intents.all()
        ],
        "sanctioned_total": blocked_total,
        "sanctioned_page": sanctioned_meta["page"],
        "sanctioned_page_size": sanctioned_meta["page_size"],
        "sanctioned_pages": sanctioned_meta["pages"],
        "sanctioned": [_public_sanction(row) for row in blocked.all()],
        "networks": sorted(SANCTION_NETWORKS),
    }


async def create_sanction(
    session: AsyncSession,
    clock: Clock,
    actor_id: UUID,
    *,
    address: str,
    network: str,
    source: str,
    reason: str = "",
) -> dict[str, object]:
    net = normalize_network(network)
    addr = normalize_sanction_address(address, net)
    src = (source or "").strip()
    if not src:
        raise AppError(400, "SANCTION_SOURCE_REQUIRED")
    if len(src) > SOURCE_MAX:
        raise AppError(400, "SANCTION_SOURCE_TOO_LONG", details={"max": SOURCE_MAX})
    note = (reason or "").strip()
    if len(note) > REASON_MAX:
        raise AppError(400, "SANCTION_REASON_TOO_LONG", details={"max": REASON_MAX})

    existing = await session.scalar(
        select(SanctionedAddress).where(SanctionedAddress.address == addr, SanctionedAddress.network == net)
    )
    if existing is not None:
        raise AppError(409, "SANCTION_ALREADY_EXISTS", details={"network": net, "source": existing.source})

    row = SanctionedAddress(
        address=addr,
        network=net,
        source=src[:SOURCE_MAX],
        reason=note[:REASON_MAX],
        created_at=clock.now(),
    )
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="sanction.create",
        target_type="sanctioned_address",
        target_id=str(row.id),
        detail=f"{net}:{_mask(addr)};source={src}",
        now=clock.now(),
    )
    return _public_sanction(row)


async def update_sanction(
    session: AsyncSession,
    clock: Clock,
    actor_id: UUID,
    sanction_id: UUID,
    *,
    source: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    row = await session.get(SanctionedAddress, sanction_id)
    if row is None:
        raise AppError(404, "SANCTION_NOT_FOUND")
    if source is not None:
        src = source.strip()
        if not src:
            raise AppError(400, "SANCTION_SOURCE_EMPTY")
        if len(src) > SOURCE_MAX:
            raise AppError(400, "SANCTION_SOURCE_TOO_LONG", details={"max": SOURCE_MAX})
        row.source = src
    if reason is not None:
        note = reason.strip()
        if len(note) > REASON_MAX:
            raise AppError(400, "SANCTION_REASON_TOO_LONG", details={"max": REASON_MAX})
        row.reason = note
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="sanction.update",
        target_type="sanctioned_address",
        target_id=str(row.id),
        detail=f"{row.network}:{_mask(row.address)}",
        now=clock.now(),
    )
    return _public_sanction(row)


async def delete_sanction(
    session: AsyncSession,
    clock: Clock,
    actor_id: UUID,
    sanction_id: UUID,
) -> dict[str, object]:
    row = await session.get(SanctionedAddress, sanction_id)
    if row is None:
        raise AppError(404, "SANCTION_NOT_FOUND")
    detail = f"{row.network}:{_mask(row.address)};source={row.source}"
    payload = _public_sanction(row)
    await session.delete(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="sanction.delete",
        target_type="sanctioned_address",
        target_id=str(sanction_id),
        detail=detail,
        now=clock.now(),
    )
    payload["deleted"] = True
    return payload


async def is_sanctioned(session: AsyncSession, address: str, network: str) -> bool:
    """供支付回调使用：规范化后再精确匹配。"""
    net = (network or "").strip().upper()
    if net not in SANCTION_NETWORKS:
        return False
    try:
        addr = normalize_sanction_address(address, net)
    except AppError:
        # 回调里的异常地址按未命中处理，避免因格式异常阻断整条流水；
        # 真正格式问题会在其它校验暴露。
        raw = (address or "").strip()
        if not raw:
            return False
        addr = raw.lower() if net == "ERC20" else raw
    row = await session.scalar(
        select(SanctionedAddress).where(SanctionedAddress.address == addr, SanctionedAddress.network == net)
    )
    return row is not None
