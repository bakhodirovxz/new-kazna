"""1C HTTP-xizmati mijozi (Basic auth). Faqat worker; hisob ma'lumoti `app.core.integrations`
dan keladi va hech qachon log/xato matniga tushmaydi (xato matnlarida faqat status/tur).

httpx: trust_env=False, redirect yo'q, TLS tekshiruvi (ixtiyoriy CA fayli), javob hajmi
chegarasi. Vaqtinchalik xatolar (tarmoq, taym-aut, 5xx) — `ConnectorUnavailableError` (Runner
qayta urinadi); format/avtorizatsiya/xizmat xatolari — `OneCError` (qayta urinilmaydi).
"""

from __future__ import annotations

import json
import ssl
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import ConfigError
from app.etl.types import ConnectorUnavailableError

TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)
MAX_BYTES = 64 * 1024 * 1024
WHERE = "1С"


class OneCError(Exception):
    """1C xizmati xatosi (success=false, 401/403, 4xx) — qayta urinilmaydi."""


class OneCFormatError(OneCError):
    """1C javobi kutilgan tuzilishda emas (HTML, JSON emas, maydon yo'q)."""


def verify_setting(ca_file: str) -> ssl.SSLContext | bool:
    """`onec_ca_file` bo'sh — tizim CA'lari; aks holda shu fayl (ichki CA)."""
    return ssl.create_default_context(cafile=ca_file) if ca_file else True


class OneCClient:
    def __init__(self, base_url: str, username: str, password: str, *,
                 verify: ssl.SSLContext | bool = True, allow_http: bool = False,
                 max_bytes: int = MAX_BYTES, timeout: httpx.Timeout = TIMEOUT,
                 transport: httpx.BaseTransport | None = None) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ConfigError("1С: адрес сервиса должен быть http(s)://")
        if parsed.scheme == "http" and not allow_http:
            raise ConfigError("1С: адрес без HTTPS запрещён настройкой сервера")
        self.base_url = base_url.rstrip("/")
        self.max_bytes = max_bytes
        self.http = httpx.Client(timeout=timeout, verify=verify, trust_env=False,
                                 follow_redirects=False, transport=transport,
                                 auth=httpx.BasicAuth(username, password),
                                 headers={"Accept": "application/json"})

    def close(self) -> None:
        self.http.close()

    def post(self, path: str, body: dict[str, Any]) -> Any:
        chunks: list[bytes] = []
        size = 0
        try:
            with self.http.stream("POST", self.base_url + path, json=body) as response:
                status = response.status_code
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise OneCFormatError(f"{WHERE} {path}: ответ больше допустимого размера")
                    chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise ConnectorUnavailableError(f"{WHERE} {path}: тайм-аут") from exc
        except httpx.TransportError as exc:
            raise ConnectorUnavailableError(f"{WHERE} {path}: {type(exc).__name__}") from exc
        if status >= 500 or status == 429:
            raise ConnectorUnavailableError(f"{WHERE} {path}: HTTP {status}")
        if status in (401, 403):
            raise OneCError(f"{WHERE} {path}: отказ в доступе (HTTP {status})")
        if status != 200:
            raise OneCError(f"{WHERE} {path}: HTTP {status}")
        try:
            return json.loads(b"".join(chunks).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OneCFormatError(f"{WHERE} {path}: ответ не JSON") from exc
