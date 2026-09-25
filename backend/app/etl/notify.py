"""ETL xabarnomalari (spec 5.4): log va ichki SMTP relay. Telegram — keyingi spec."""

from __future__ import annotations

import re
import smtplib
import ssl
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Literal, Protocol

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger("ugekazna.notify")
Kind = Literal["etl_failed", "etl_quality", "control_totals", "stale_data"]

# Oddiy email manzil tekshiruvi (app/core/config.py dagi bilan bir xil): bo'shliq,
# vergul, <>, ikkinchi @ — sarlavha in'ektsiyasi (CR/LF) oldini oladi.
_ADDR_RE = re.compile(r"^[^\s,<>@]+@[^\s,<>@]+\.[^\s,<>@]+$")


def _validate_recipients(recipients: Sequence[str]) -> list[str]:
    result = list(recipients)
    invalid = [r for r in result if not _ADDR_RE.match(r)]
    if invalid:
        raise ValueError(f"yaroqsiz email manzil(lar): {invalid!r}")
    return result


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
        ssl: bool = False,
        timeout: float = 10.0,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
        smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL,
    ) -> None:
        self.host = host
        self.port = port
        self.sender = sender
        self.recipients = _validate_recipients(recipients)
        self.username = username
        self.password = password
        self.starttls = starttls
        self.ssl = ssl
        self.timeout = timeout
        self._factory = smtp_factory
        self._ssl_factory = smtp_ssl_factory

    def notify(self, notification: Notification) -> None:
        if self.password and not (self.starttls or self.ssl):
            # Parolni shifrlanmagan ulanish orqali yubormaymiz (plaintext AUTH).
            log.warning(
                "email_notify_refused_plaintext_auth", kind=notification.kind, host=self.host
            )
            return
        message = EmailMessage()
        message["Subject"] = f"[UGEKAZNA] {_one_line(notification.subject)}"
        message["From"] = self.sender
        message["To"] = ", ".join(formataddr(("", r)) for r in self.recipients)
        message.set_content(notification.body)
        try:
            if self.ssl:
                context = ssl.create_default_context()
                with self._ssl_factory(
                    self.host, self.port, context=context, timeout=self.timeout
                ) as smtp:
                    if self.password:
                        smtp.login(self.username or self.sender, self.password)
                    smtp.send_message(message)
            else:
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
                ssl=settings.smtp_ssl,
            )
        )
    return CompositeNotifier(notifiers)
