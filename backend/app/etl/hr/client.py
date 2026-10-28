"""HR API mijozi (hr-api.uzgidro.uz): `X-Api-Key` sarlavhasi bilan faqat GET, login yo'q.

Token faqat shu obyekt xotirasida (admin panel sirlari, `hr.api_key`); repr/xato/log'ga
chiqmaydi. Faqat https, TLS tekshiruvi (ixtiyoriy korporativ CA), trust_env=False, redirect yo'q,
javob hajmi chegarasi. Xato matniga javob tanasi kirmaydi — faqat HTTP kod va `code` maydoni
(oq ro'yxat).
"""

from __future__ import annotations

import json
import re
import ssl
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import ConfigError
from app.etl.types import ConnectorUnavailableError

# Oylik so'rovlar bir necha soniya oladi (HR hujjati) — o'qish uchun keng vaqt.
TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
MAX_BYTES = 8 * 1024 * 1024
WHERE = "HR API"
_CODE = re.compile(r"^[a-z_]{1,40}$")


def ca_context(path: str) -> ssl.SSLContext | bool:
    """Korporativ CA fayli bo'lsa — shu bilan tekshiriladi, aks holda tizim CA'lari."""
    if path and Path(path).is_file() and Path(path).stat().st_size > 0:
        return ssl.create_default_context(cafile=path)
    return True


class HrApiError(ValueError):
    """Qayta urinilmaydigan xato (kalit, format, 4xx)."""


class HrApiClient:
    def __init__(self, base_url: str, api_key: str, *, verify: ssl.SSLContext | bool = True,
                 proxy: str = "", transport: httpx.BaseTransport | None = None,
                 timeout: httpx.Timeout = TIMEOUT, max_bytes: int = MAX_BYTES) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigError("hr.base_url https:// manzil bo'lishi kerak")
        if not api_key:
            raise ConfigError("hr.api_key siri bo'sh")
        self.max_bytes = max_bytes
        self.http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, verify=verify, trust_env=False,
            follow_redirects=False, proxy=proxy or None, transport=transport,
            headers={"Accept": "application/json", "X-Api-Key": api_key})

    def __repr__(self) -> str:
        return f"HrApiClient({self.http.base_url!s})"

    def close(self) -> None:
        self.http.close()

    def _read(self, path: str, params: dict[str, str] | None) -> tuple[int, bytes]:
        chunks: list[bytes] = []
        size = 0
        try:
            with self.http.stream("GET", path, params=params) as response:
                status = response.status_code
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise HrApiError(f"{WHERE} {path}: ответ больше {self.max_bytes} байт")
                    chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise ConnectorUnavailableError(f"{WHERE} {path}: тайм-аут") from exc
        except httpx.TransportError as exc:
            raise ConnectorUnavailableError(f"{WHERE} {path}: {type(exc).__name__}") from exc
        return status, b"".join(chunks)

    @staticmethod
    def _json(raw: bytes, path: str) -> Any:
        try:
            return json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HrApiError(f"{WHERE} {path}: ответ не JSON") from exc

    @staticmethod
    def _code(raw: bytes) -> str:
        try:
            code = json.loads(raw.decode("utf-8-sig")).get("code")
        except (UnicodeDecodeError, ValueError, AttributeError):
            return ""
        return f", {code}" if isinstance(code, str) and _CODE.fullmatch(code) else ""

    def get(self, path: str, params: dict[str, str] | None = None) -> Any:
        status, raw = self._read(path, params)
        if status in (401, 403):
            raise HrApiError(f"{WHERE} {path}: доступ запрещён (HTTP {status}), "
                             "проверьте API-ключ hr.api_key")
        if status >= 500 or status in (404, 429):  # 404: manzil/token doirasi
            raise ConnectorUnavailableError(f"{WHERE} {path}: HTTP {status}{self._code(raw)}")
        if not 200 <= status < 300:
            raise HrApiError(f"{WHERE} {path}: HTTP {status}{self._code(raw)}")
        return self._json(raw, path)
