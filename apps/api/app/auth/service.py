"""注册、登录、会话、邮箱与二次验证。"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pyotp

from app.admin.audit import append_audit
from app.auth.crypto import decrypt_text, encrypt_text
from app.auth.emailer import EmailSender, OutboundEmail
from app.auth.passwords import (
    dummy_password_hash,
    hash_password,
    validate_email,
    validate_password,
    verify_password,
)
from app.auth.rbac import ROLE_IDS, seed_rbac
from app.auth.repository import AuthRepository, new_device, new_profile
from app.auth.tokens import as_utc, digest, new_secret, same_digest
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.auth import (
    EmailChangeToken,
    EmailVerificationToken,
    MfaChallenge,
    PasswordResetToken,
    Session,
    User,
    UserProfile,
    UserRole,
)

SEND_INTERVAL = timedelta(seconds=60)
TOKEN_TTL = timedelta(minutes=30)
CHALLENGE_TTL = timedelta(minutes=5)
LOCK_DURATION = timedelta(minutes=15)
DAILY_LIMIT = 10
MAX_ATTEMPTS = 5


@dataclass
class AuthResult:
    data: dict[str, object]
    session_token: str | None = None
    clear_session: bool = False


class AuthService:
    def __init__(self, repo: AuthRepository, settings: Settings, clock: Clock, email: EmailSender) -> None:
        self.repo = repo
        self.settings = settings
        self.clock = clock
        self.email = email

    async def prepare(self) -> None:
        await seed_rbac(self.repo.session)

    async def register(self, email: str, password: str, accept_terms: bool, accept_privacy: bool, ip: str, user_agent: str) -> AuthResult:
        if not accept_terms or not accept_privacy:
            raise AppError(400, "AUTH_TERMS_REQUIRED")
        normalized = validate_email(email)
        validate_password(password, normalized)
        await self.prepare()
        now = self.clock.now()
        if ip and await self.repo.count_registrations_since(ip, now - timedelta(hours=1)) >= self.settings.register_ip_hourly_limit:
            raise AppError(429, "AUTH_REGISTER_RATE_LIMITED")
        if await self.repo.get_user_by_email(normalized) is not None:
            raise AppError(409, "EMAIL_TAKEN")
        user = User(
            email=email.strip(),
            email_normalized=normalized,
            password_hash=hash_password(password),
            status="pending_verification",
            failed_login_count=0,
            totp_enabled=False,
            terms_version=self.settings.terms_version,
            terms_accepted_at=now,
            privacy_version=self.settings.privacy_version,
            privacy_accepted_at=now,
            register_ip=ip or None,
            register_user_agent=user_agent[:1000] or None,
            created_at=now,
            updated_at=now,
        )
        self.repo.add(user)
        await self.repo.session.flush()
        self.repo.add(new_profile(user.id, now))
        self.repo.add(UserRole(user_id=user.id, role_id=UUID(ROLE_IDS["user"]), granted_at=now))
        delivery = await self._send_verification(user)
        return AuthResult({"user_id": str(user.id), "email_delivery": delivery})

    async def resend_verification(self, email: str) -> AuthResult:
        await self.prepare()
        user = await self._existing_user(email)
        if user is None or user.status == "deleted":
            return AuthResult({"email_delivery": "unconfigured" if not self.email.configured else "accepted"})
        if user.status == "active":
            return AuthResult({"email_delivery": "already_verified"})
        delivery = await self._send_verification(user)
        return AuthResult({"email_delivery": delivery})

    async def verify_email(self, email: str, token: str) -> AuthResult:
        await self.prepare()
        user = await self._require_user(email)
        row = await self.repo.latest_verification(user.id)
        await self._accept_token(row, token)
        user.status = "active"
        user.updated_at = self.clock.now()
        return AuthResult({"user_id": str(user.id), "status": user.status})

    async def login(self, email: str, password: str, ip: str, user_agent: str) -> AuthResult:
        await self.prepare()
        normalized = validate_email(email)
        user = await self.repo.get_user_by_email(normalized)
        if user is None or user.status == "deleted":
            verify_password(password, dummy_password_hash())
            raise AppError(401, "AUTH_BAD_CREDENTIALS")
        now = self.clock.now()
        if user.locked_until is not None and as_utc(user.locked_until) > now:
            raise AppError(403, "ACCOUNT_LOCKED")
        if user.locked_until is not None and as_utc(user.locked_until) <= now:
            user.failed_login_count = 0
            user.locked_until = None
        if not verify_password(password, user.password_hash):
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_ATTEMPTS:
                user.locked_until = now + LOCK_DURATION
            await self._keep()
            raise AppError(401, "AUTH_BAD_CREDENTIALS")
        user.failed_login_count = 0
        user.locked_until = None
        if user.status == "pending_verification":
            raise AppError(403, "EMAIL_NOT_VERIFIED")
        if user.status == "frozen":
            raise AppError(403, "ACCOUNT_FROZEN")
        if user.totp_enabled:
            secret = new_secret()
            self.repo.add(
                MfaChallenge(
                    user_id=user.id,
                    token_hash=digest(secret),
                    expires_at=now + CHALLENGE_TTL,
                    attempt_count=0,
                    created_at=now,
                )
            )
            return AuthResult({"totp_required": True, "challenge": secret})
        session_token = await self._open_session(user, ip, user_agent)
        return AuthResult({"totp_required": False, "user": self._public_user(user)}, session_token=session_token)

    async def verify_totp_login(self, challenge: str, code: str, ip: str, user_agent: str) -> AuthResult:
        await self.prepare()
        now = self.clock.now()
        row = await self.repo.get_challenge(digest(challenge))
        if row is None or row.consumed_at is not None or row.attempt_count >= MAX_ATTEMPTS or as_utc(row.expires_at) <= now:
            raise AppError(400, "AUTH_TOTP_CHALLENGE_EXPIRED")
        user = await self.repo.get_user(row.user_id)
        if user is None or not await self._consume_second_factor(user, code, now):
            row.attempt_count += 1
            if row.attempt_count >= MAX_ATTEMPTS:
                row.consumed_at = now
            await self._keep()
            raise AppError(400, "AUTH_TOTP_BAD_CODE")
        row.consumed_at = now
        session_token = await self._open_session(user, ip, user_agent)
        return AuthResult({"totp_required": False, "user": self._public_user(user)}, session_token=session_token)

    async def logout(self, token_hash: str) -> AuthResult:
        row = await self.repo.get_session_by_hash(token_hash)
        if row is not None and row.revoked_at is None:
            row.revoked_at = self.clock.now()
        return AuthResult({"logged_out": True}, clear_session=True)

    async def me(self, user: User) -> AuthResult:
        return AuthResult({"user": self._public_user(user), "roles": await self.repo.role_codes(user.id)})

    async def profile(self, user: User) -> AuthResult:
        row = await self.repo.get_profile(user.id)
        if row is None:
            raise AppError(404, "PROFILE_NOT_FOUND")
        return AuthResult(self._public_profile(row))

    async def update_profile(self, user: User, display_name: str, timezone: str, locale: str) -> AuthResult:
        if locale not in {"zh-CN", "zh-TW", "en"}:
            raise AppError(400, "LOCALE_INVALID")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise AppError(400, "TIMEZONE_INVALID") from exc
        row = await self.repo.get_profile(user.id)
        if row is None:
            raise AppError(404, "PROFILE_NOT_FOUND")
        row.display_name = display_name.strip()
        row.timezone = timezone
        row.locale = locale
        row.updated_at = self.clock.now()
        return AuthResult(self._public_profile(row))

    async def list_devices(self, user: User) -> AuthResult:
        rows = await self.repo.list_devices(user.id)
        return AuthResult(
            {
                "devices": [
                    {
                        "id": str(row.id),
                        "user_agent": row.user_agent,
                        "ip": row.ip,
                        "last_seen_at": as_utc(row.last_seen_at).isoformat(),
                    }
                    for row in rows
                ]
            }
        )

    @staticmethod
    def _public_profile(row: UserProfile) -> dict[str, object]:
        return {
            "display_name": row.display_name,
            "timezone": row.timezone,
            "locale": row.locale,
            "updated_at": as_utc(row.updated_at).isoformat(),
        }

    async def list_sessions(self, user: User, current_id: UUID) -> AuthResult:
        rows = await self.repo.list_sessions(user.id)
        data = [
            {
                "id": str(row.id),
                "created_at": as_utc(row.created_at).isoformat(),
                "last_seen_at": as_utc(row.last_seen_at).isoformat(),
                "user_agent": row.user_agent or "",
                "current": row.id == current_id,
                "revoked": row.revoked_at is not None,
            }
            for row in rows
        ]
        return AuthResult({"sessions": data})

    async def revoke_session(self, user: User, session_id: UUID) -> AuthResult:
        row = await self.repo.revoke_session(session_id, user.id, self.clock.now())
        if row is None:
            raise AppError(404, "SESSION_NOT_FOUND")
        return AuthResult({"revoked": True})

    async def forgot_password(self, email: str) -> AuthResult:
        await self.prepare()
        if not self.email.configured:
            return AuthResult({"email_delivery": "unconfigured"})
        user = await self._existing_user(email)
        if user is None or user.status == "deleted":
            return AuthResult({"email_delivery": "accepted"})
        now = self.clock.now()
        await self._assert_rate(await self.repo.count_resets_since(user.id, now - timedelta(days=1)), await self.repo.latest_reset_at(user.id), now)
        secret = new_secret()
        self.repo.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=digest(secret),
                expires_at=now + TOKEN_TTL,
                attempt_count=0,
                created_at=now,
            )
        )
        link = f"{self.settings.public_app_url}/reset-password?email={quote(user.email_normalized)}"
        await self._send(
            user.email,
            "Reset your password",
            f"Reset token: {secret}\nOpen: {link}\n",
        )
        return AuthResult({"email_delivery": "sent"})

    async def reset_password(self, email: str, token: str, password: str) -> AuthResult:
        await self.prepare()
        normalized = validate_email(email)
        validate_password(password, normalized)
        user = await self._require_user(email)
        row = await self.repo.latest_reset(user.id)
        await self._accept_token(row, token)
        user.password_hash = hash_password(password)
        user.failed_login_count = 0
        user.locked_until = None
        user.updated_at = self.clock.now()
        await self.repo.revoke_other_sessions(user.id, None, self.clock.now())
        return AuthResult({"reset": True})

    async def change_password(self, user: User, current_password: str, password: str, keep_session_id: UUID) -> AuthResult:
        if not verify_password(current_password, user.password_hash):
            raise AppError(401, "AUTH_BAD_CURRENT_PASSWORD")
        validate_password(password, user.email_normalized)
        user.password_hash = hash_password(password)
        user.updated_at = self.clock.now()
        await self.repo.revoke_other_sessions(user.id, keep_session_id, self.clock.now())
        if self.email.configured:
            await self._send(
                user.email,
                "Password changed",
                "Your password was just changed. If this was not you, reset it immediately.\n",
            )
        return AuthResult({"changed": True, "email_delivery": "sent" if self.email.configured else "unconfigured"})

    async def request_email_change(self, user: User, password: str, new_email: str) -> AuthResult:
        if not verify_password(password, user.password_hash):
            raise AppError(401, "AUTH_BAD_CURRENT_PASSWORD")
        normalized = validate_email(new_email)
        if normalized == user.email_normalized:
            raise AppError(400, "EMAIL_SAME_AS_CURRENT")
        if await self.repo.get_user_by_email(normalized) is not None:
            raise AppError(409, "EMAIL_TAKEN")
        if not self.email.configured:
            return AuthResult({"email_delivery": "unconfigured"})
        now = self.clock.now()
        await self._assert_rate(
            await self.repo.count_email_changes_since(user.id, now - timedelta(days=1)),
            await self.repo.latest_email_change_at(user.id),
            now,
        )
        secret = new_secret()
        self.repo.add(
            EmailChangeToken(
                user_id=user.id,
                new_email=normalized,
                token_hash=digest(secret),
                expires_at=now + TOKEN_TTL,
                attempt_count=0,
                created_at=now,
            )
        )
        await self._send(new_email.strip(), "Confirm your new email", f"Confirmation token: {secret}\n")
        return AuthResult({"email_delivery": "sent"})

    async def confirm_email_change(self, user: User, token: str) -> AuthResult:
        row = await self.repo.latest_email_change(user.id)
        await self._accept_token(row, token)
        if row is None:
            raise AppError(400, "TOKEN_INVALID")
        old_email = user.email
        user.email = row.new_email
        user.email_normalized = row.new_email
        user.updated_at = self.clock.now()
        notice = "unconfigured"
        if self.email.configured:
            try:
                await self._send(
                    old_email,
                    "Email address changed",
                    f"Your sign-in email is now {row.new_email}. If this was not you, contact support immediately.\n",
                )
                notice = "sent"
            except AppError:
                notice = "failed"
        return AuthResult({"email": user.email, "notice_delivery": notice})

    async def setup_totp(self, user: User) -> AuthResult:
        if user.totp_enabled:
            raise AppError(409, "TOTP_ALREADY_ENABLED")
        secret = pyotp.random_base32()
        user.totp_secret_encrypted = encrypt_text(self.settings.encryption_master_key, secret)
        uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="ForgeAPI")
        return AuthResult({"secret": secret, "otpauth_uri": uri})

    async def enable_totp(self, user: User, code: str) -> AuthResult:
        if user.totp_enabled or not user.totp_secret_encrypted:
            raise AppError(400, "TOTP_SEED_REQUIRED")
        secret = decrypt_text(
            self.settings.encryption_master_key,
            user.totp_secret_encrypted,
            code="TOTP_DECRYPT_FAILED",
        )
        if not pyotp.TOTP(secret).verify(code, valid_window=1):
            raise AppError(400, "AUTH_TOTP_BAD_CODE")
        now = self.clock.now()
        user.totp_enabled = True
        user.updated_at = now
        codes = [new_secret()[:16] for _ in range(8)]
        await self.repo.replace_recovery_codes(user.id, [digest(item) for item in codes], now)
        return AuthResult({"recovery_codes": codes})

    async def disable_totp(self, user: User, password: str, code: str) -> AuthResult:
        if not verify_password(password, user.password_hash):
            raise AppError(401, "AUTH_BAD_CURRENT_PASSWORD")
        if not user.totp_enabled or not await self._consume_second_factor(user, code, self.clock.now()):
            raise AppError(400, "AUTH_TOTP_BAD_CODE")
        user.totp_enabled = False
        user.totp_secret_encrypted = None
        user.updated_at = self.clock.now()
        await self.repo.clear_recovery_codes(user.id)
        return AuthResult({"totp_enabled": False})

    async def bootstrap(self, token: str, email: str, password: str) -> AuthResult:
        await self.prepare()
        path = Path(self.settings.admin_init_token_path)
        if not path.is_file():
            consumed = path.with_name(path.name + ".consumed")
            if consumed.is_file():
                raise AppError(403, "BOOTSTRAP_TOKEN_USED")
            raise AppError(403, "BOOTSTRAP_TOKEN_MISSING")
        expected = path.read_text(encoding="utf-8").strip().lower()
        actual = hashlib.sha256(token.encode()).hexdigest()
        if not hmac.compare_digest(expected, actual):
            raise AppError(403, "BOOTSTRAP_TOKEN_INVALID")
        if await self.repo.count_superadmins() > 0:
            raise AppError(409, "BOOTSTRAP_ALREADY_DONE")
        normalized = validate_email(email)
        validate_password(password, normalized)
        now = self.clock.now()
        user = User(
            email=email.strip(),
            email_normalized=normalized,
            password_hash=hash_password(password),
            status="active",
            failed_login_count=0,
            totp_enabled=False,
            terms_version=self.settings.terms_version,
            terms_accepted_at=now,
            privacy_version=self.settings.privacy_version,
            privacy_accepted_at=now,
            created_at=now,
            updated_at=now,
        )
        self.repo.add(user)
        await self.repo.session.flush()
        self.repo.add(new_profile(user.id, now))
        self.repo.add(UserRole(user_id=user.id, role_id=UUID(ROLE_IDS["superadmin"]), granted_at=now))
        consumed = path.with_name(path.name + ".consumed")
        path.replace(consumed)
        return AuthResult({"user_id": str(user.id), "role": "superadmin"})

    async def assign_role(self, actor: User, target_id: UUID, role_code: str) -> AuthResult:
        if role_code == "superadmin":
            raise AppError(403, "ROLE_SUPERADMIN_FORBIDDEN")
        if role_code not in ROLE_IDS:
            raise AppError(400, "ROLE_NOT_FOUND")
        target = await self.repo.get_user(target_id)
        if target is None:
            raise AppError(404, "USER_NOT_FOUND")
        role_id = UUID(ROLE_IDS[role_code])
        codes = await self.repo.role_codes(target.id)
        added = role_code not in codes
        if added:
            self.repo.add(UserRole(user_id=target.id, role_id=role_id, granted_by=actor.id, granted_at=self.clock.now()))
        await append_audit(
            self.repo.session,
            actor_id=actor.id,
            action="rbac.assign",
            target_type="user",
            target_id=str(target.id),
            detail=f"role={role_code};added={'true' if added else 'false'}",
            now=self.clock.now(),
        )
        return AuthResult({"user_id": str(target.id), "role": role_code})

    async def _send_verification(self, user: User) -> str:
        if not self.email.configured:
            return "unconfigured"
        now = self.clock.now()
        await self._assert_rate(
            await self.repo.count_verifications_since(user.id, now - timedelta(days=1)),
            await self.repo.latest_verification_at(user.id),
            now,
        )
        secret = new_secret()
        self.repo.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=digest(secret),
                expires_at=now + TOKEN_TTL,
                attempt_count=0,
                created_at=now,
            )
        )
        link = (
            f"{self.settings.public_app_url}/verify-email"
            f"?email={quote(user.email_normalized)}&token={quote(secret)}"
        )
        await self._send(user.email, "Verify your email", f"Verification token: {secret}\nOpen: {link}\n")
        return "sent"

    async def _send(self, to: str, subject: str, text: str) -> None:
        await self.email.send(OutboundEmail(to=to, subject=subject, text=text))

    async def _assert_rate(self, count: int, latest: datetime | None, now: datetime) -> None:
        if latest is not None and now - as_utc(latest) < SEND_INTERVAL:
            raise AppError(429, "MAIL_SEND_RATE_LIMITED")
        if count >= DAILY_LIMIT:
            raise AppError(429, "MAIL_DAILY_LIMIT")

    async def _keep(self) -> None:
        await self.repo.session.commit()

    async def _accept_token(
        self,
        row: EmailVerificationToken | PasswordResetToken | EmailChangeToken | None,
        token: str,
    ) -> None:
        now = self.clock.now()
        if row is None:
            raise AppError(400, "TOKEN_INVALID")
        if row.attempt_count >= MAX_ATTEMPTS:
            row.consumed_at = now
            await self._keep()
            raise AppError(400, "TOKEN_TOO_MANY_ATTEMPTS")
        if as_utc(row.expires_at) <= now:
            row.attempt_count += 1
            if row.attempt_count >= MAX_ATTEMPTS:
                row.consumed_at = now
            await self._keep()
            raise AppError(400, "TOKEN_EXPIRED")
        if not same_digest(row.token_hash, token):
            row.attempt_count += 1
            if row.attempt_count >= MAX_ATTEMPTS:
                row.consumed_at = now
            await self._keep()
            raise AppError(400, "TOKEN_MISMATCH")
        row.consumed_at = now

    async def _open_session(self, user: User, ip: str, user_agent: str) -> str:
        now = self.clock.now()
        secret = new_secret()
        self.repo.add(
            Session(
                user_id=user.id,
                token_hash=digest(secret),
                created_at=now,
                last_seen_at=now,
                absolute_expires_at=now + timedelta(hours=self.settings.session_absolute_hours),
                idle_expires_at=now + timedelta(hours=self.settings.session_idle_hours),
                created_ip=ip or None,
                last_seen_ip=ip or None,
                user_agent=user_agent[:1000] or None,
            )
        )
        self.repo.add(new_device(user.id, user_agent, ip, now))
        return secret

    async def _consume_second_factor(self, user: User, code: str, now: datetime) -> bool:
        if not user.totp_secret_encrypted:
            return False
        secret = decrypt_text(
            self.settings.encryption_master_key,
            user.totp_secret_encrypted,
            code="TOTP_DECRYPT_FAILED",
        )
        if pyotp.TOTP(secret).verify(code, valid_window=1):
            return True
        recovery = await self.repo.unused_recovery(user.id, digest(code))
        if recovery is None:
            return False
        recovery.used_at = now
        return True

    async def _existing_user(self, email: str) -> User | None:
        try:
            normalized = validate_email(email)
        except AppError:
            return None
        return await self.repo.get_user_by_email(normalized)

    async def _require_user(self, email: str) -> User:
        user = await self._existing_user(email)
        if user is None or user.status == "deleted":
            raise AppError(400, "TOKEN_INVALID")
        return user

    @staticmethod
    def _public_user(user: User) -> dict[str, object]:
        return {
            "id": str(user.id),
            "email": user.email,
            "status": user.status,
            "totp_enabled": user.totp_enabled,
        }
