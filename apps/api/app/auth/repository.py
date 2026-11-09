"""身份数据访问。业务判断放在 service。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import (
    EmailChangeToken,
    EmailVerificationToken,
    LoginDevice,
    MfaChallenge,
    PasswordResetToken,
    Permission,
    Role,
    RolePermission,
    Session,
    TotpRecoveryCode,
    User,
    UserProfile,
    UserRole,
)


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_profile(self, user_id: UUID) -> UserProfile | None:
        return await self.session.get(UserProfile, user_id)

    async def list_devices(self, user_id: UUID) -> list[LoginDevice]:
        result = await self.session.execute(
            select(LoginDevice).where(LoginDevice.user_id == user_id).order_by(LoginDevice.last_seen_at.desc())
        )
        return list(result.scalars().all())

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_user_by_email(self, email_normalized: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email_normalized == email_normalized))
        return result.scalar_one_or_none()

    def add(self, row: object) -> None:
        self.session.add(row)

    async def count_registrations_since(self, ip: str, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .where(User.register_ip == ip, User.created_at >= since)
        )
        return int(result.scalar_one())

    async def count_superadmins(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(UserRole)
            .where(UserRole.role_id == UUID("00000000-0000-4000-8000-000000000007"))
        )
        return int(result.scalar_one())

    async def role_codes(self, user_id: UUID) -> list[str]:
        result = await self.session.execute(
            select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        )
        return list(result.scalars().all())

    async def permission_codes(self, user_id: UUID) -> set[str]:
        result = await self.session.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )
        return set(result.scalars().all())

    async def get_session_by_hash(self, token_hash: str) -> Session | None:
        result = await self.session.execute(select(Session).where(Session.token_hash == token_hash))
        return result.scalar_one_or_none()

    async def list_sessions(self, user_id: UUID) -> list[Session]:
        result = await self.session.execute(
            select(Session).where(Session.user_id == user_id).order_by(Session.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_session(self, session_id: UUID, user_id: UUID, when: datetime) -> Session | None:
        result = await self.session.execute(
            select(Session).where(Session.id == session_id, Session.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row is not None and row.revoked_at is None:
            row.revoked_at = when
        return row

    async def revoke_other_sessions(self, user_id: UUID, keep_id: UUID | None, when: datetime) -> None:
        statement = update(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
        if keep_id is not None:
            statement = statement.where(Session.id != keep_id)
        await self.session.execute(statement.values(revoked_at=when))

    async def latest_verification(self, user_id: UUID) -> EmailVerificationToken | None:
        result = await self.session.execute(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.user_id == user_id, EmailVerificationToken.consumed_at.is_(None))
            .order_by(EmailVerificationToken.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_verifications_since(self, user_id: UUID, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(EmailVerificationToken)
            .where(EmailVerificationToken.user_id == user_id, EmailVerificationToken.created_at >= since)
        )
        return int(result.scalar_one())

    async def latest_verification_at(self, user_id: UUID) -> datetime | None:
        result = await self.session.execute(
            select(func.max(EmailVerificationToken.created_at)).where(EmailVerificationToken.user_id == user_id)
        )
        value = result.scalar_one()
        return value if isinstance(value, datetime) else None

    async def latest_reset(self, user_id: UUID) -> PasswordResetToken | None:
        result = await self.session.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.consumed_at.is_(None))
            .order_by(PasswordResetToken.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_resets_since(self, user_id: UUID, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.created_at >= since)
        )
        return int(result.scalar_one())

    async def latest_reset_at(self, user_id: UUID) -> datetime | None:
        result = await self.session.execute(
            select(func.max(PasswordResetToken.created_at)).where(PasswordResetToken.user_id == user_id)
        )
        value = result.scalar_one()
        return value if isinstance(value, datetime) else None

    async def latest_email_change(self, user_id: UUID) -> EmailChangeToken | None:
        result = await self.session.execute(
            select(EmailChangeToken)
            .where(EmailChangeToken.user_id == user_id, EmailChangeToken.consumed_at.is_(None))
            .order_by(EmailChangeToken.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_email_changes_since(self, user_id: UUID, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(EmailChangeToken)
            .where(EmailChangeToken.user_id == user_id, EmailChangeToken.created_at >= since)
        )
        return int(result.scalar_one())

    async def latest_email_change_at(self, user_id: UUID) -> datetime | None:
        result = await self.session.execute(
            select(func.max(EmailChangeToken.created_at)).where(EmailChangeToken.user_id == user_id)
        )
        value = result.scalar_one()
        return value if isinstance(value, datetime) else None

    async def get_challenge(self, token_hash: str) -> MfaChallenge | None:
        result = await self.session.execute(select(MfaChallenge).where(MfaChallenge.token_hash == token_hash))
        return result.scalar_one_or_none()

    async def replace_recovery_codes(self, user_id: UUID, code_hashes: list[str], now: datetime) -> None:
        existing = await self.session.execute(select(TotpRecoveryCode).where(TotpRecoveryCode.user_id == user_id))
        for row in existing.scalars().all():
            await self.session.delete(row)
        for code_hash in code_hashes:
            self.session.add(
                TotpRecoveryCode(user_id=user_id, code_hash=code_hash, created_at=now)
            )

    async def unused_recovery(self, user_id: UUID, code_hash: str) -> TotpRecoveryCode | None:
        result = await self.session.execute(
            select(TotpRecoveryCode).where(
                TotpRecoveryCode.user_id == user_id,
                TotpRecoveryCode.code_hash == code_hash,
                TotpRecoveryCode.used_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def clear_recovery_codes(self, user_id: UUID) -> None:
        existing = await self.session.execute(select(TotpRecoveryCode).where(TotpRecoveryCode.user_id == user_id))
        for row in existing.scalars().all():
            await self.session.delete(row)


def new_profile(user_id: UUID, now: datetime) -> UserProfile:
    return UserProfile(user_id=user_id, display_name="", timezone="UTC", locale="zh-CN", created_at=now, updated_at=now)


def new_device(user_id: UUID, user_agent: str, ip: str, now: datetime) -> LoginDevice:
    return LoginDevice(user_id=user_id, user_agent=user_agent[:1000], ip=ip[:64], last_seen_at=now, created_at=now)
