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

from app.core import integrations, sysconfig
from app.core.db import get_engine
from app.core.logging import get_logger

log = get_logger("ugekazna.notify")
# "etl_row_errors" — task-8 controller ruling: merge tomonidan bloklovchi bo'lmagan kod bilan
# rad etilgan qatorlar (masalan `negative_amount`, `missing_value`) sifat tekshiruvini
# to'xtatmaydi, lekin ko'rinmas bo'lib qolmasligi kerak — faqat sonlar bilan xabar qilinadi.
Kind = Literal["etl_failed", "etl_quality", "control_totals", "stale_data", "etl_row_errors",
            "ops_check"]

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


@dataclass(frozen=True, slots=True)
class SmtpConfig:
    host: str
    port: int
    sender: str
    recipients: list[str]
    username: str
    password: str
    starttls: bool
    ssl: bool


def smtp_config() -> SmtpConfig | None:
    """Joriy SMTP sozlamasi (panel > env > standart); host yoki qabul qiluvchi yo'q — None."""
    with get_engine("app").connect() as conn:
        host = str(sysconfig.current(conn, "smtp.host"))
        recipients = list(sysconfig.current(conn, "notify.email_to"))
        if not host or not recipients:
            return None
        return SmtpConfig(
            host=host, port=int(sysconfig.current(conn, "smtp.port")),
            sender=str(sysconfig.current(conn, "smtp.from")), recipients=recipients,
            username=str(sysconfig.current(conn, "smtp.user")),
            password=integrations.secret(conn, "smtp.password"),
            starttls=bool(sysconfig.current(conn, "smtp.starttls")),
            ssl=bool(sysconfig.current(conn, "smtp.ssl")))


class LiveEmailNotifier:
    """Har xabarda joriy sozlama — panel o'zgarishi worker'ni qayta ishga tushirmasdan ishlaydi."""

    def __init__(self, loader: Callable[[], SmtpConfig | None] = smtp_config,
                 smtp_factory: Callable[..., Any] = smtplib.SMTP,
                 smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL) -> None:
        self._loader = loader
        self._factory = smtp_factory
        self._ssl_factory = smtp_ssl_factory

    def notify(self, notification: Notification) -> None:
        cfg = self._loader()
        if cfg is None:
            return
        EmailNotifier(host=cfg.host, port=cfg.port, sender=cfg.sender, recipients=cfg.recipients,
                      username=cfg.username, password=cfg.password, starttls=cfg.starttls,
                      ssl=cfg.ssl, smtp_factory=self._factory,
                      smtp_ssl_factory=self._ssl_factory).notify(notification)


def smtp_probe(loader: Callable[[], SmtpConfig | None] = smtp_config,
               smtp_factory: Callable[..., Any] = smtplib.SMTP,
               smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL) -> str:
    """Ulanish + TLS + login (xat yuborilmaydi). Faqat xavfsiz kod qaytaradi."""
    cfg = loader()
    if cfg is None:
        return "not_configured"
    if cfg.password and not (cfg.starttls or cfg.ssl):
        return "insecure_refused"
    context = ssl.create_default_context()
    try:
        if cfg.ssl:
            client = smtp_ssl_factory(cfg.host, cfg.port, context=context, timeout=10.0)
        else:
            client = smtp_factory(cfg.host, cfg.port, timeout=10.0)
        with client as smtp:
            if cfg.starttls and not cfg.ssl:
                smtp.starttls(context=context)
            if cfg.password:
                smtp.login(cfg.username or cfg.sender, cfg.password)
            smtp.noop()
    except smtplib.SMTPAuthenticationError:
        return "auth_failed"
    except ssl.SSLError:
        return "tls_failed"
    except TimeoutError:
        return "timeout"
    except smtplib.SMTPException:
        return "protocol_error"
    except OSError:
        return "connect_failed"
    return "ok"


def build_notifier() -> Notifier:
    return CompositeNotifier([LogNotifier(), LiveEmailNotifier()])
