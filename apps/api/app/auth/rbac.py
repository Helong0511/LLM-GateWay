"""权限常量和角色种子。单一角色不得同时拥有退款发起和退款执行。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import Permission, Role, RolePermission

ROLE_IDS: dict[str, str] = {
    "user": "00000000-0000-4000-8000-000000000001",
    "support": "00000000-0000-4000-8000-000000000002",
    "finance": "00000000-0000-4000-8000-000000000003",
    "operator": "00000000-0000-4000-8000-000000000004",
    "model_ops": "00000000-0000-4000-8000-000000000005",
    "admin": "00000000-0000-4000-8000-000000000006",
    "superadmin": "00000000-0000-4000-8000-000000000007",
}

# 机器可读展示名（英文）；控制台按 role code 走前端 i18n。
ROLE_NAMES: dict[str, str] = {
    "user": "User",
    "support": "Support",
    "finance": "Finance",
    "operator": "Operator",
    "model_ops": "Model ops",
    "admin": "Admin",
    "superadmin": "Superadmin",
}

PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    ("00000000-0000-4000-8000-000000000101", "admin:access", "Access admin APIs"),
    ("00000000-0000-4000-8000-000000000102", "user:ban", "Freeze or unfreeze users"),
    ("00000000-0000-4000-8000-000000000103", "ledger:adjust", "Adjust ledger"),
    ("00000000-0000-4000-8000-000000000104", "provider:credential:read", "Read provider credentials"),
    ("00000000-0000-4000-8000-000000000105", "rbac:assign", "Assign roles"),
    ("00000000-0000-4000-8000-000000000106", "refund:request", "Request refunds"),
    ("00000000-0000-4000-8000-000000000107", "refund:execute", "Execute refunds"),
    ("00000000-0000-4000-8000-000000000108", "provider:manage", "Manage providers and endpoint allowlist"),
    ("00000000-0000-4000-8000-000000000109", "model:publish", "Confirm and publish models"),
)

ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    "user": (),
    # support / operator 之前没有任何权限，登录后台必然 403，角色形同虚设。
    # 两者都只给只读后台入口，写操作仍按最小权限单独授予。
    "support": ("admin:access",),
    "finance": ("refund:request",),
    "operator": ("admin:access",),
    "model_ops": ("provider:credential:read", "provider:manage", "model:publish", "admin:access"),
    "admin": ("admin:access", "refund:execute", "user:ban", "rbac:assign", "provider:manage", "model:publish"),
    # superadmin 是兜底角色，但**不能**同时拥有 refund:request，
    # 否则退款「申请/复核/执行」三方分离的约束会被自己破掉。
    "superadmin": (
        "admin:access",
        "user:ban",
        "rbac:assign",
        "ledger:adjust",
        "provider:credential:read",
        "provider:manage",
        "model:publish",
        "refund:execute",
    ),
}


def refund_duties_are_split() -> bool:
    request = "refund:request"
    execute = "refund:execute"
    return all(not (request in grants and execute in grants) for grants in ROLE_GRANTS.values())


async def seed_rbac(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for code, role_key in ROLE_IDS.items():
        if await session.get(Role, UUID(role_key)) is None:
            session.add(
                Role(
                    id=UUID(role_key),
                    code=code,
                    name=ROLE_NAMES[code],
                    description="",
                    is_system=True,
                    created_at=now,
                )
            )
    for permission_id, code, description in PERMISSIONS:
        if await session.get(Permission, UUID(permission_id)) is None:
            session.add(
                Permission(
                    id=UUID(permission_id),
                    code=code,
                    description=description,
                    created_at=now,
                )
            )
    await session.flush()
    permission_ids = {code: UUID(item_id) for item_id, code, _description in PERMISSIONS}
    for role_code, grants in ROLE_GRANTS.items():
        role_id = UUID(ROLE_IDS[role_code])
        for permission_code in grants:
            granted_id = permission_ids[permission_code]
            existing = await session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == granted_id,
                )
            )
            if existing.scalar_one_or_none() is None:
                session.add(RolePermission(role_id=role_id, permission_id=granted_id))
    await session.flush()
