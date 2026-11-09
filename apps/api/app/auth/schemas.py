"""认证请求体。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    accept_terms: bool
    accept_privacy: bool


class EmailBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class VerifyEmailBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    token: str = Field(min_length=16, max_length=256)


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class TotpLoginBody(BaseModel):
    challenge: str = Field(min_length=16, max_length=256)
    code: str = Field(min_length=6, max_length=64)


class ResetPasswordBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    token: str = Field(min_length=16, max_length=256)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class EmailChangeBody(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    new_email: str = Field(min_length=3, max_length=320)


class TokenBody(BaseModel):
    token: str = Field(min_length=16, max_length=256)


class CodeBody(BaseModel):
    code: str = Field(min_length=6, max_length=64)


class DisableTotpBody(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=64)


class ProfileBody(BaseModel):
    display_name: str = Field(max_length=128)
    timezone: str = Field(min_length=1, max_length=64)
    locale: str = Field(min_length=2, max_length=16)


class BootstrapBody(BaseModel):
    token: str = Field(min_length=8, max_length=256)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class AssignRoleBody(BaseModel):
    role_code: str = Field(min_length=2, max_length=64)
