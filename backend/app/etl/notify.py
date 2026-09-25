"""ETL xabarnomalari (spec 5.4): log va ichki SMTP relay. Telegram — keyingi spec."""

from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Literal, Protocol

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger("ugekazna.notify")
Kind = Literal["etl_failed", "etl_quality", "control_totals", "stale_data"]


@dataclass(frozen=True, slots=True)
class Notification:
    kind: Kind
    subject: str
    body: str


class Notifier(Protocol):
    def notify(self, notification: Notification) -> None: ...


class LogNotifier:
    def notify(self, notification: Notification) -> None:
        log.warning(
            "notification",
            kind=notification.kind,
            subject=notification.subject,
            body=notification.body,
        )


def _one_line(value: str) -> str:
    # Sarlavhaga CR/LF tushmasin (header injection).
    return " ".join(value.split())[:200]


class EmailNotifier:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        recipients: Sequence[str],
        username: str = "",
        password: str = "",
        starttls: bool = True,
        timeout: float = 10.0,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
    ) -> None:
        self.host = host
        self.port = port
        self.sender = sender
        self.recipients = list(recipients)
        self.username = username
        self.password = password
        self.starttls = starttls
        self.timeout = timeout
        self._factory = smtp_factory

    def notify(self, notification: Notification) -> None:
        message = EmailMessage()
        message["Subject"] = f"[UGEKAZNA] {_one_line(notification.subject)}"
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        message.set_content(notification.body)
        try:
            with self._factory(self.host, self.port, timeout=self.timeout) as smtp:
                if self.starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if self.password:
                    smtp.login(self.username or self.sender, self.password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            # Xabarnoma xatosi ETL'ni yiqitmasligi kerak.
            log.error("notify_email_failed", kind=notification.kind, error=type(exc).__name__)


class CompositeNotifier:
    def __init__(self, notifiers: Sequence[Notifier]) -> None:
        self.notifiers = tuple(notifiers)

    def notify(self, notification: Notification) -> None:
        for notifier in self.notifiers:
            try:
                notifier.notify(notification)
            except Exception as exc:  # bitta kanal qolganlarini to'xtatmaydi
                log.error("notifier_failed", notifier=type(notifier).__name__,
                          error=type(exc).__name__)


def build_notifier(settings: Settings) -> Notifier:
    notifiers: list[Notifier] = [LogNotifier()]
    if settings.smtp_host and settings.smtp_recipients:
        notifiers.append(
            EmailNotifier(
                host=settings.smtp_host,
                port=settings.smtp_port,
                sender=settings.smtp_from,
                recipients=settings.smtp_recipients,
                username=settings.smtp_user,
                password=settings.smtp_password.get_secret_value(),
                starttls=settings.smtp_starttls,
            )
        )
    return CompositeNotifier(notifiers)
