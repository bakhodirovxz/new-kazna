"""ETL xabarnomalari (spec 5.4): log va ichki SMTP relay. Telegram — keyingi spec."""

from __future__ import annotations

import contextlib
import re
import smtplib
import socket
import ssl
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Literal, Protocol

from sqlalchemy.exc import SQLAlchemyError

from app.core import integrations, sysconfig
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.logging import get_logger

log = get_logger("ugekazna.notify")
# "etl_row_errors" — task-8 controller ruling: merge tomonidan bloklovchi bo'lmagan kod bilan
# rad etilgan qatorlar (masalan `negative_amount`, `missing_value`) sifat tekshiruvini
# to'xtatmaydi, lekin ko'rinmas bo'lib qolmasligi kerak — faqat sonlar bilan xabar qilinadi.
Kind = Literal["etl_failed", "etl_quality", "control_totals", "stale_data", "etl_row_errors",
            "ops_check", "bank_rows_rejected"]

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


SMTP_DEADLINE = 30.0  # s: butun SMTP seansi (socket timeout'i har amalga alohida — M7)


def _abort(client: Any) -> None:
    """Muddati o'tgan seans: recv'da osilgan ipni uyg'otish uchun socket yopiladi."""
    with contextlib.suppress(Exception):  # yopish xatosi muhim emas
        sock = getattr(client, "sock", None)
        if sock is not None:
            sock.shutdown(socket.SHUT_RDWR)
    with contextlib.suppress(Exception):
        client.close()


def _within_deadline(fn: Callable[[], Any], clients: list[Any]) -> Any:
    """`fn` ni SMTP_DEADLINE ichida bajaradi, aks holda `clients` (fn qo'shgan mijozlar)
    socket'i yopilib TimeoutError ko'tariladi."""
    out: list[Any] = []
    err: list[BaseException] = []

    def run() -> None:
        try:
            out.append(fn())
        except BaseException as exc:
            err.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(SMTP_DEADLINE)
    if thread.is_alive():
        for client in clients:
            _abort(client)
        raise TimeoutError("smtp deadline")
    if err:
        raise err[0]
    return out[0] if out else None


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

        clients: list[Any] = []

        def send() -> None:
            if self.ssl:
                client = self._ssl_factory(
                    self.host, self.port, context=ssl.create_default_context(),
                    timeout=self.timeout)
            else:
                client = self._factory(self.host, self.port, timeout=self.timeout)
            clients.append(client)
            with client as smtp:
                if self.starttls and not self.ssl:
                    smtp.starttls(context=ssl.create_default_context())
                if self.password:
                    smtp.login(self.username or self.sender, self.password)
                smtp.send_message(message)

        try:
            _within_deadline(send, clients)
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
    password: str = field(repr=False)
    starttls: bool
    ssl: bool


def _env_smtp_config() -> SmtpConfig | None:
    """DB ishlamaganda: faqat server konfiguratsiyasi (env host + env sir — izchil juftlik)."""
    cfg = get_settings()
    if not cfg.smtp_host or not cfg.smtp_recipients:
        return None
    return SmtpConfig(
        host=cfg.smtp_host, port=cfg.smtp_port, sender=cfg.smtp_from,
        recipients=cfg.smtp_recipients, username=cfg.smtp_user,
        password=cfg.smtp_password.get_secret_value(), starttls=cfg.smtp_starttls,
        ssl=cfg.smtp_ssl)


def smtp_config() -> SmtpConfig | None:
    """Joriy SMTP sozlamasi (panel > env > standart); host yoki qabul qiluvchi yo'q — None.
    DB ishlamasa — env'dan (A04b.R2): "DB unreachable" va ETL xatosi xabarlari yo'qolmasin."""
    try:
        return _db_smtp_config()
    except SQLAlchemyError as exc:
        log.warning("smtp_config_db_unavailable", error=type(exc).__name__)
        return _env_smtp_config()


def _db_smtp_config() -> SmtpConfig | None:
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

    clients: list[Any] = []

    def run() -> None:
        if cfg.ssl:
            client = smtp_ssl_factory(cfg.host, cfg.port, context=context, timeout=10.0)
        else:
            client = smtp_factory(cfg.host, cfg.port, timeout=10.0)
        clients.append(client)
        with client as smtp:
            if cfg.starttls and not cfg.ssl:
                smtp.starttls(context=context)
            if cfg.password:
                smtp.login(cfg.username or cfg.sender, cfg.password)
            smtp.noop()

    try:
        _within_deadline(run, clients)
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
    # Aylanma importdan qochish: telegram moduli Notification'ni shu fayldan oladi.
    from app.etl.telegram import TelegramNotifier

    return CompositeNotifier([LogNotifier(), LiveEmailNotifier(), TelegramNotifier()])
