"""Outgoing email (invitations). SMTP to Mailpit in development; tests swap in a fake."""

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol

from riven_api.config import get_settings


class Mailer(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpMailer:
    def __init__(self, host: str, port: int, sender: str) -> None:
        self._host, self._port, self._sender = host, port, sender

    async def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self._sender, to, subject
        message.set_content(body)
        await asyncio.to_thread(self._deliver, message)

    def _deliver(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            smtp.send_message(message)


def get_mailer() -> Mailer:
    settings = get_settings()
    return SmtpMailer(settings.smtp_host, settings.smtp_port, settings.mail_from)
