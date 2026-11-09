"""邮件发送。未配置时明确失败，不把未发出的信记成已发送。"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import Settings
from app.core.errors import AppError


@dataclass(frozen=True)
class OutboundEmail:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    configured: bool

    async def send(self, message: OutboundEmail) -> None:
        """发送一封纯文本邮件。"""


class UnconfiguredEmailSender:
    configured = False

    async def send(self, message: OutboundEmail) -> None:
        raise AppError(503, "MAIL_NOT_CONFIGURED")


class CaptureEmailSender:
    """测试收件箱。只留在内存里，不写日志。"""

    configured = True

    def __init__(self) -> None:
        self.messages: list[OutboundEmail] = []

    async def send(self, message: OutboundEmail) -> None:
        self.messages.append(message)


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.configured = bool(settings.smtp_host.strip())

    async def send(self, message: OutboundEmail) -> None:
        if not self.configured:
            raise AppError(503, "MAIL_NOT_CONFIGURED")
        email = EmailMessage()
        email["From"] = self.settings.smtp_from
        email["To"] = message.to
        email["Subject"] = message.subject
        email.set_content(message.text)
        try:
            await aiosmtplib.send(
                email,
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                username=self.settings.smtp_user or None,
                password=self.settings.smtp_password or None,
                start_tls=self.settings.smtp_tls,
            )
        except Exception as exc:
            raise AppError(503, "MAIL_SEND_FAILED") from exc


def build_email_sender(settings: Settings) -> EmailSender:
    if not settings.smtp_host.strip():
        return UnconfiguredEmailSender()
    return SmtpEmailSender(settings)
