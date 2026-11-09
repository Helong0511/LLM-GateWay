"""认证 HTTP 接口。路径不带版本段。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.auth.deps import (
    assert_browser_origin,
    client_ip,
    get_current_user,
    get_service,
    optional_session_row,
    user_agent,
)
from app.auth.schemas import (
    BootstrapBody,
    ChangePasswordBody,
    CodeBody,
    DisableTotpBody,
    EmailBody,
    EmailChangeBody,
    LoginBody,
    ProfileBody,
    RegisterBody,
    ResetPasswordBody,
    TokenBody,
    TotpLoginBody,
    VerifyEmailBody,
)
from app.auth.service import AuthResult, AuthService
from app.auth.tokens import as_utc, digest
from app.core.config import Settings
from app.core.errors import AppError, success
from app.db.models.auth import Session, User

router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(assert_browser_origin)])


def _apply_cookie(response: Response, settings: Settings, result: AuthResult) -> None:
    secure = settings.cookie_secure or settings.app_env == "production"
    name = settings.session_cookie_name
    if result.clear_session:
        response.delete_cookie(name, path="/", secure=secure, httponly=True, samesite="lax")
    elif result.session_token:
        response.set_cookie(
            key=name,
            value=result.session_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=settings.session_absolute_hours * 3600,
        )


@router.post("/register")
async def register(
    body: RegisterBody,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.register(
        body.email, body.password, body.accept_terms, body.accept_privacy, client_ip(request), user_agent(request)
    )
    _apply_cookie(response, request.app.state.settings, result)
    return success(request, result.data)


@router.post("/resend-verification")
async def resend_verification(
    body: EmailBody,
    request: Request,
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.resend_verification(body.email)
    return success(request, result.data)


@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailBody,
    request: Request,
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.verify_email(body.email, body.token)
    return success(request, result.data)


@router.post("/login")
async def login(
    body: LoginBody,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.login(body.email, body.password, client_ip(request), user_agent(request))
    _apply_cookie(response, request.app.state.settings, result)
    return success(request, result.data)


@router.post("/totp/verify")
async def verify_totp_login(
    body: TotpLoginBody,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.verify_totp_login(body.challenge, body.code, client_ip(request), user_agent(request))
    _apply_cookie(response, request.app.state.settings, result)
    return success(request, result.data)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    raw = request.cookies.get(settings.session_cookie_name, "")
    result = await service.logout(digest(raw) if raw else "")
    _apply_cookie(response, settings, result)
    return success(request, result.data)


@router.get("/me")
async def me(
    request: Request,
    user: User = Depends(get_current_user),
    row: Session | None = Depends(optional_session_row),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.me(user)
    settings: Settings = request.app.state.settings
    data = dict(result.data)
    data["session_policy"] = {
        "idle_hours": settings.session_idle_hours,
        "absolute_hours": settings.session_absolute_hours,
    }
    if row is not None:
        data["session"] = {
            "idle_expires_at": as_utc(row.idle_expires_at).isoformat(),
            "absolute_expires_at": as_utc(row.absolute_expires_at).isoformat(),
        }
    return success(request, data)


@router.get("/profile")
async def profile(
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.profile(user)
    return success(request, result.data)


@router.patch("/profile")
async def update_profile(
    body: ProfileBody,
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.update_profile(user, body.display_name, body.timezone, body.locale)
    return success(request, result.data)


@router.get("/devices")
async def devices(
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.list_devices(user)
    return success(request, result.data)


@router.get("/sessions")
async def sessions(
    request: Request,
    user: User = Depends(get_current_user),
    row: Session | None = Depends(optional_session_row),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    if row is None:
        return success(request, {"sessions": []})
    result = await service.list_sessions(user, row.id)
    return success(request, result.data)


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.revoke_session(user, session_id)
    return success(request, result.data)


@router.post("/forgot-password")
async def forgot_password(
    body: EmailBody,
    request: Request,
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.forgot_password(body.email)
    return success(request, result.data)


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordBody,
    request: Request,
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.reset_password(body.email, body.token, body.password)
    return success(request, result.data)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordBody,
    request: Request,
    user: User = Depends(get_current_user),
    row: Session | None = Depends(optional_session_row),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    if row is None:
        raise AppError(401, "UNAUTHENTICATED")
    result = await service.change_password(user, body.current_password, body.password, row.id)
    return success(request, result.data)


@router.post("/email-change")
async def request_email_change(
    body: EmailChangeBody,
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.request_email_change(user, body.password, body.new_email)
    return success(request, result.data)


@router.post("/email-change/confirm")
async def confirm_email_change(
    body: TokenBody,
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.confirm_email_change(user, body.token)
    return success(request, result.data)


@router.post("/totp/setup")
async def setup_totp(
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.setup_totp(user)
    return success(request, result.data)


@router.post("/totp/enable")
async def enable_totp(
    body: CodeBody,
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.enable_totp(user, body.code)
    return success(request, result.data)


@router.post("/totp/disable")
async def disable_totp(
    body: DisableTotpBody,
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.disable_totp(user, body.password, body.code)
    return success(request, result.data)


@router.post("/bootstrap")
async def bootstrap(
    body: BootstrapBody,
    request: Request,
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.bootstrap(body.token, body.email, body.password)
    return success(request, result.data)
