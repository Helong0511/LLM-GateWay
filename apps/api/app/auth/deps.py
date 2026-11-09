"""当前用户、权限和来源检查。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.emailer import EmailSender
from app.auth.repository import AuthRepository
from app.auth.service import AuthService
from app.auth.tokens import as_utc, digest
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.auth import Session, User
from app.db.session import get_db


def client_ip(request: Request) -> str:
    if request.client is None:
        return ""
    return request.client.host


def user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


async def assert_browser_origin(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    if origin is None:
        return
    settings: Settings = request.app.state.settings
    if origin not in settings.cors_origin_list:
        raise AppError(403, "ORIGIN_FORBIDDEN")


def get_service(request: Request, db: AsyncSession = Depends(get_db)) -> AuthService:
    sender: EmailSender = request.app.state.email_sender
    clock: Clock = request.app.state.clock
    settings: Settings = request.app.state.settings
    return AuthService(AuthRepository(db), settings, clock, sender)


async def optional_session_row(request: Request, db: AsyncSession = Depends(get_db)) -> Session | None:
    settings: Settings = request.app.state.settings
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        return None
    row = await AuthRepository(db).get_session_by_hash(digest(raw))
    now = request.app.state.clock.now()
    if row is None or row.revoked_at is not None:
        # Cookie 还在但会话已失效：清掉浏览器 Cookie，避免“看起来仍登录”
        request.state.clear_session_cookie = True
        return None
    if as_utc(row.absolute_expires_at) <= now or as_utc(row.idle_expires_at) <= now:
        row.revoked_at = now
        request.state.clear_session_cookie = True
        return None
    row.last_seen_at = now
    row.last_seen_ip = client_ip(request) or row.last_seen_ip
    # 滑动空闲续期，但不得超过绝对过期时间
    idle = now + timedelta(hours=settings.session_idle_hours)
    absolute = as_utc(row.absolute_expires_at)
    row.idle_expires_at = idle if idle < absolute else absolute
    return row


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    row: Session | None = Depends(optional_session_row),
) -> User:
    if row is None:
        raise AppError(401, "UNAUTHENTICATED")
    user = await AuthRepository(db).get_user(row.user_id)
    if user is None or user.status in {"deleted", "frozen"}:
        raise AppError(401, "UNAUTHENTICATED")
    return user


def require_permission(*codes: str) -> Callable[..., Awaitable[User]]:
    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        granted = await AuthRepository(db).permission_codes(user.id)
        if not set(codes).issubset(granted):
            raise AppError(403, "FORBIDDEN")
        return user

    return checker


def require_any_permission(*codes: str) -> Callable[..., Awaitable[User]]:
    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        granted = await AuthRepository(db).permission_codes(user.id)
        if granted.isdisjoint(codes):
            raise AppError(403, "FORBIDDEN")
        return user

    return checker
