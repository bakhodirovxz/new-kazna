"""Telegram Bot API — faqat chiquvchi xabarlar (TZ 8 «Телеграм-бот», S2 spec 9).

Token URL yo'lida (`/bot<token>/sendMessage`) bo'ladi, shuning uchun: httpx logger'i WARNING
darajasiga tushiriladi (INFO so'rov logida URL bor), istisnolar `from None` bilan va faqat
HTTP kodi yoki xato turi bilan qayta ko'tariladi — token hech qayerga yozilmaydi.
Matn — oddiy (parse_mode yo'q: markup in'ektsiyasi yo'q), 4096 belgigacha.
"""

from __future__ import annotations

import logging
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.core import integrations, sysconfig
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.core.integrations import TELEGRAM_TOKEN_RE
from app.core.logging import get_logger
from app.etl.notify import Notification

MAX_TEXT = 4096
MAX_RETRY_AFTER = 30
TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)
log = get_logger("ugekazna.telegram")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class TelegramError(Exception):
    """Xabar yuborilmadi (matnda token ham, URL ham yo'q)."""


def _retry_after(response: httpx.Response) -> float:
    try:
        value = float(response.json()["parameters"]["retry_after"])
    except (ValueError, KeyError, TypeError):
        value = 1.0
    return max(0.0, min(value, float(MAX_RETRY_AFTER)))


class TelegramClient:
    def __init__(self, token: str, *, api_base: str = "https://api.telegram.org",
                 proxy: str = "", transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not TELEGRAM_TOKEN_RE.fullmatch(token):
            raise ConfigError("telegram_bot_token formati noto'g'ri")
        self._path = f"/bot{token}/sendMessage"
        self.sleep = sleep
        self.http = httpx.Client(
            base_url=api_base.rstrip("/"), timeout=TIMEOUT, verify=True, trust_env=False,
            follow_redirects=False, proxy=proxy or None, transport=transport)

    def close(self) -> None:
        self.http.close()

    def send(self, chat_id: int, text: str) -> None:
        body = {"chat_id": chat_id, "text": text[:MAX_TEXT], "disable_web_page_preview": True}
        status = 0
        for attempt in range(2):
            try:
                response = self.http.post(self._path, json=body)
            except httpx.HTTPError as exc:
                raise TelegramError(f"Telegram: {type(exc).__name__}") from None
            status = response.status_code
            if status == 200:
                return
            if attempt == 0 and status == 429:
                self.sleep(_retry_after(response))
                continue
            if attempt == 0 and status >= 500:
                self.sleep(2.0)
                continue
            break
        raise TelegramError(f"Telegram: HTTP {status}")


    def check(self) -> str:
        """`getMe` (xabar yuborilmaydi) -> faqat xavfsiz kod (U8)."""
        try:
            response = self.http.get(self._path.replace("/sendMessage", "/getMe"))
        except httpx.TimeoutException:
            return "timeout"
        except httpx.ConnectError as exc:
            return "tls_failed" if isinstance(exc.__cause__, ssl.SSLError) else "connect_failed"
        except httpx.HTTPError:
            return "connect_failed"
        if response.status_code == 200:
            return "ok"
        return "auth_failed" if response.status_code in (401, 403, 404) else "http_error"


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    token: str
    chats: list[int]


def telegram_config() -> TelegramConfig | None:
    """Joriy sozlama (panel): token (shifrlangan sir) + chat'lar; to'liq emas/DB yo'q - None."""
    try:
        with get_engine("app").connect() as conn:
            chats = [int(c) for c in sysconfig.current(conn, "telegram.chat_ids")]
            token = integrations.secret(conn, "telegram.bot_token")
    except SQLAlchemyError as exc:
        log.warning("telegram_config_db_unavailable", error=type(exc).__name__)
        return None
    return TelegramConfig(token, chats) if token and chats else None


def make_client(cfg: TelegramConfig) -> TelegramClient:
    settings = get_settings()
    return TelegramClient(cfg.token, api_base=settings.telegram_api_base,
                          proxy=settings.egress_proxy)


def telegram_probe(loader: Callable[[], TelegramConfig | None] = telegram_config,
                   factory: Callable[[TelegramConfig], TelegramClient] = make_client) -> str:
    cfg = loader()
    if cfg is None:
        return "not_configured"
    try:
        client = factory(cfg)
    except ConfigError:
        return "format_error"
    try:
        return client.check()
    finally:
        client.close()


class TelegramNotifier:
    """2-reja Notifier: ETL xatolari va ogohlantirishlarini chat'larga yuboradi. Har yuborishda
    joriy sozlama o'qiladi (LiveEmailNotifier namunasi) - panel o'zgarishi darhol kuchga kiradi."""

    def __init__(self, loader: Callable[[], TelegramConfig | None] = telegram_config,
                 factory: Callable[[TelegramConfig], TelegramClient] = make_client) -> None:
        self._loader = loader
        self._factory = factory

    def notify(self, notification: Notification) -> None:
        cfg = self._loader()
        if cfg is None:
            return
        text = f"UGEKAZNA: {notification.subject}\n\n{notification.body}"
        try:
            client = self._factory(cfg)
        except ConfigError as exc:
            log.error("telegram_config_invalid", error=str(exc))
            return
        try:
            for chat in cfg.chats:
                try:
                    client.send(chat, text)
                except TelegramError as exc:
                    log.error("telegram_notify_failed", kind=notification.kind, error=str(exc))
        finally:
            client.close()
