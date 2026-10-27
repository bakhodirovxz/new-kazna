"""1C HTTP mijozi: POST JSON, Basic auth, TLS tekshiruvi, BOM, javob o'lchami chegarasi.

Xatolar ikki turga bo'linadi: vaqtincha (tarmoq, tayм-aut, 5xx, 429) →
OneCUnavailableError (ConnectorUnavailableError) — ETL runner qayta urinadi; qolganlari (format,
4xx, qayta yo'naltirish, kesilgan javob) → OneCError (ValueError) — qayta urinilmaydi. Har xatoda
`code` — probe uchun xavfsiz kod. Xabarlarda hisob ma'lumotlari va javob tanasining katta qismi
bo'lmaydi.
"""

from __future__ import annotations

import json
import ssl
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy.engine import Connection

from app.core import integrations, sysconfig
from app.core.config import ConfigError, get_settings
from app.core.setting_types import onec_url_host
from app.etl.types import ConnectorUnavailableError

TIMEOUT = httpx.Timeout(connect=5.0, read=180.0, write=30.0, pool=5.0)
MAX_BYTES = 64 * 1024 * 1024
DEADLINE = 300.0  # bitta so'rov uchun umumiy chegara (sekin "tomchilatib" javob qulfni ushlamasin)
BOM = b"\xef\xbb\xbf"


class OneCError(ValueError):
    """Qayta urinilmaydigan 1C xatosi."""

    code = "http_error"


class OneCAuthError(OneCError):
    code = "auth_failed"


class OneCFormatError(OneCError):
    """Javob JSON emas yoki kutilgan tuzilmada emas."""

    code = "format_error"


class OneCTruncatedError(OneCError):
    """Javob `limit` ga yetdi — ma'lumot kesilgan bo'lishi mumkin (sahifalash yo'q)."""


class OneCUnavailableError(ConnectorUnavailableError):
    """Vaqtincha xato (qayta uriniladi)."""

    def __init__(self, message: str, code: str = "connect_failed") -> None:
        super().__init__(message)
        self.code = code


class OneCCaError(ConfigError):
    """CA to'plami o'qib bo'lmadi."""


def verify_setting(ca_file: str) -> ssl.SSLContext | bool:
    path = Path(ca_file)
    if not ca_file or not path.is_file() or path.stat().st_size == 0:
        return True  # httpx standarti: certifi CA to'plami (OS do'koni EMAS)
    try:
        return ssl.create_default_context(cafile=str(path))
    except (ssl.SSLError, OSError) as exc:
        raise OneCCaError(f"onec_ca_bundle o'qib bo'lmadi: {type(exc).__name__}") from exc


def _preview(text: str) -> str:
    clean = "".join(ch if ch.isprintable() else " " for ch in text[:80])
    return clean.strip()


def parse_json(raw: bytes, path: str) -> Any:
    if raw.startswith(BOM):
        raw = raw[len(BOM):]
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise OneCFormatError(f"1С {path}: ответ не в UTF-8") from exc
    if not text:
        raise OneCFormatError(f"1С {path}: пустой ответ")
    try:
        return json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise OneCFormatError(f"1С {path}: ответ не JSON (начало: «{_preview(text)}»)") from exc


@dataclass(frozen=True, slots=True)
class OneCConfig:
    """Ulanish konfiguratsiyasi: manzil/limit/sirlar — panel (U6), CA/allow_http — Settings."""

    base_url: str
    username: str = field(repr=False)
    password: str = field(repr=False)
    max_bytes: int = MAX_BYTES
    ca_file: str = ""
    allow_http: bool = False

    @classmethod
    def load(cls, conn: Connection) -> OneCConfig:
        if not integrations.configured(conn, "onec"):
            raise ConfigError("1С не настроена: Администрирование → Интеграции → 1С")
        settings = get_settings()
        return cls(
            base_url=str(sysconfig.current(conn, "onec.base_url")),
            username=integrations.secret(conn, "onec.username"),
            password=integrations.secret(conn, "onec.password"),
            max_bytes=int(sysconfig.current(conn, "onec.max_mb")) * 1024 * 1024,
            ca_file=settings.onec_ca_file, allow_http=settings.onec_allow_http)


class OneCClient:
    def __init__(self, config: OneCConfig, *, timeout: httpx.Timeout = TIMEOUT,
                 deadline: float = DEADLINE,
                 transport: httpx.BaseTransport | None = None) -> None:
        parsed = urlsplit(config.base_url)
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ConfigError("onec.base_url noto'g'ri")
        try:
            onec_url_host(config.base_url)
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        if parsed.scheme == "http" and not config.allow_http:
            raise ConfigError("onec.base_url https bo'lishi shart (yoki ONEC_ALLOW_HTTP=true)")
        if not config.username or not config.password:
            raise ConfigError("onec.username/onec.password bo'sh")
        self.insecure = parsed.scheme == "http"
        self.max_bytes = config.max_bytes
        self.deadline = deadline
        self.http = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            auth=httpx.BasicAuth(config.username, config.password), timeout=timeout,
            verify=verify_setting(config.ca_file), trust_env=False, follow_redirects=False,
            transport=transport, headers={"Accept": "application/json"})

    def close(self) -> None:
        self.http.close()

    def post(self, path: str, body: Mapping[str, Any]) -> Any:
        chunks: list[bytes] = []
        size = 0
        started = time.monotonic()
        try:
            with self.http.stream("POST", path, json=dict(body)) as response:
                status = response.status_code
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise OneCFormatError(f"1С {path}: ответ больше {self.max_bytes} байт")
                    chunks.append(chunk)
                    if time.monotonic() - started > self.deadline:
                        raise OneCUnavailableError(f"1С {path}: тайм-аут (общий)", "timeout")
        except httpx.TimeoutException as exc:
            raise OneCUnavailableError(f"1С {path}: тайм-аут", "timeout") from exc
        except httpx.TransportError as exc:
            tls = isinstance(exc.__cause__, ssl.SSLError) or "CERTIFICATE" in str(exc).upper()
            raise OneCUnavailableError(f"1С {path}: {type(exc).__name__}",
                                       "tls_failed" if tls else "connect_failed") from exc
        if status >= 500 or status == 429:
            raise OneCUnavailableError(f"1С {path}: HTTP {status}", "http_error")
        if status in (401, 403):
            raise OneCAuthError(
                f"1С {path}: доступ запрещён (HTTP {status}), проверьте учётную запись")
        if not 200 <= status < 300:
            raise OneCError(f"1С {path}: HTTP {status}")
        return parse_json(b"".join(chunks), path)
