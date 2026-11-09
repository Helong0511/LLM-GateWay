"""管理侧用户列表和冻结。不返回密码。"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import append_audit
from app.auth.rbac import ROLE_NAMES
from app.core.errors import AppError
from app.core.paging import clamp_page, page_meta, page_offset
from app.db.models.auth import Role, User, UserRole
from app.keys.entitlements import parse_models

_MUTABLE = {"active", "frozen"}


async def list_users(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    status: str | None,
    q: str | None = None,
) -> dict[str, object]:
    page, page_size = clamp_page(page, page_size)
    filters = []
    if status:
        if status not in {"pending_verification", "active", "frozen", "deleted"}:
            raise AppError(400, "USER_FILTER_STATUS_INVALID")
        filters.append(User.status == status)
    needle = (q or "").strip().lower()
    if needle:
        if len(needle) > 128:
            raise AppError(400, "USER_SEARCH_TOO_LONG")
        filters.append(User.email_normalized.contains(needle))
    total = int(await session.scalar(select(func.count()).select_from(User).where(*filters)) or 0)
    rows = list(
        await session.scalars(
            select(User)
            .where(*filters)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
    )
    # 必须返回角色 code（如 user/support），与分配/撤销接口一致；中文名由前端展示。
    role_codes: dict[UUID, list[str]] = {row.id: [] for row in rows}
    if rows:
        grants = await session.execute(
            select(UserRole.user_id, Role.code)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id.in_([row.id for row in rows]))
        )
        for user_id, code in grants.all():
            role_codes.setdefault(user_id, []).append(str(code))
    return {
        **page_meta(page, page_size, total),
        "users": [
            {
                "id": str(row.id),
                "email": row.email,
                "status": row.status,
                "roles": role_codes.get(row.id, []),
                "role_labels": [ROLE_NAMES.get(code, code) for code in role_codes.get(row.id, [])],
                "allowed_models": parse_models(row.allowed_models),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


async def set_user_status(
    session: AsyncSession,
    *,
    actor: User,
    user_id: UUID,
    status: str,
    now: datetime,
) -> dict[str, str]:
    if status not in _MUTABLE:
        raise AppError(400, "USER_STATUS_INVALID")
    if actor.id == user_id:
        raise AppError(400, "USER_CANNOT_FREEZE_SELF")
    target = await session.get(User, user_id)
    if target is None or target.status == "deleted":
        raise AppError(404, "USER_NOT_FOUND")
    if target.status not in _MUTABLE:
        raise AppError(400, "USER_STATUS_TYPE_FORBIDDEN")
    if target.status != status:
        target.status = status
        target.updated_at = now
        await append_audit(
            session,
            actor_id=actor.id,
            action="user.unfreeze" if status == "active" else "user.freeze",
            target_type="user",
            target_id=str(target.id),
            detail=f"status={status}",
            now=now,
        )
    return {"id": str(target.id), "status": target.status}


async def set_user_models(
    session: AsyncSession,
    *,
    actor: User,
    user_id: UUID,
    models: list[str],
    now: datetime,
) -> dict[str, object]:
    """设置账号级可用模型；空列表表示未显式配置，回退到套餐范围。"""
    target = await session.get(User, user_id)
    if target is None or target.status == "deleted":
        raise AppError(404, "USER_NOT_FOUND")
    cleaned = list(dict.fromkeys(item.strip() for item in models if item and item.strip()))
    target.allowed_models = json.dumps(cleaned, ensure_ascii=False)
    target.updated_at = now
    await append_audit(
        session,
        actor_id=actor.id,
        action="user.models",
        target_type="user",
        target_id=str(target.id),
        detail=f"models={len(cleaned)}",
        now=now,
    )
    return {"id": str(target.id), "allowed_models": cleaned}
