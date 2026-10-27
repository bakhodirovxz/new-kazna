"""HR API mijozi (S4 spec 3.3): server tomonida login, token faqat shu obyekt xotirasida.

Eski dashboard (proxy.php `hr_token`) bilan bir xil oqim: POST /auth/login (form-urlencoded) →
access_token + expires_in; so'rovlarga `Authorization: Bearer`. Token muddati tugashidan 60 s
oldin yoki 401 javobida bir marta yangilanadi. Faqat https, TLS tekshiruvi (ixtiyoriy
korporativ CA), trust_env=False, redirect yo'q, javob hajmi chegarasi. Xato matnlariga javob
tanasi, token yoki parol yozilmaydi.
"""

from __future__ import annotations

import json
import ssl
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import ConfigError
from app.etl.types import ConnectorUnavailableError

TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
MAX_BYTES = 8 * 1024 * 1024
LOGIN_PATH = "/auth/login"
_DEFAULT_TTL = 3600
WHERE = "HR API"


def ca_context(path: str) -> ssl.SSLContext | bool:
    """Korporativ CA fayli bo'lsa — shu bilan tekshiriladi, aks holda tizim CA'lari."""
    if path and Path(path).is_file() and Path(path).stat().st_size > 0:
        return ssl.create_default_context(cafile=path)
    return True


class HrApiError(ValueError):
    """Qayta urinilmaydigan xato (hisob, format, 4xx)."""


class HrApiClient:
    def __init__(self, base_url: str, username: str, password: str, *,
                 verify: ssl.SSLContext | bool = True, proxy: str = "",
                 transport: httpx.BaseTransport | None = None, timeout: httpx.Timeout = TIMEOUT,
                 max_bytes: int = MAX_BYTES, clock: Callable[[], float] = time.monotonic) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigError("HR_BASE_URL https:// manzil bo'lishi kerak")
        if not username or not password:
            raise ConfigError("hr_username/hr_password sirlari bo'sh")
        self._username = username
        self._password = password
        self._token: str | None = None
        self._expires = 0.0
        self._clock = clock
        self.max_bytes = max_bytes
        self.http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, verify=verify, trust_env=False,
            follow_redirects=False, proxy=proxy or None, transport=transport,
            headers={"Accept": "application/json"})

    def __repr__(self) -> str:
        return f"HrApiClient({self.http.base_url!s})"

    def close(self) -> None:
        self.http.close()

    def _read(self, method: str, path: str, **kw: Any) -> tuple[int, bytes]:
        chunks: list[bytes] = []
        size = 0
        try:
            with self.http.stream(method, path, **kw) as response:
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
        if status >= 500 or status == 429:
            raise ConnectorUnavailableError(f"{WHERE} {path}: HTTP {status}")
        return status, b"".join(chunks)

    @staticmethod
    def _json(raw: bytes, path: str) -> Any:
        try:
            return json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HrApiError(f"{WHERE} {path}: ответ не JSON") from exc

    def login(self) -> None:
        """Faqat kirish (probe: ma'lumot so'ralmaydi)."""
        status, raw = self._read("POST", LOGIN_PATH,
                                 data={"username": self._username, "password": self._password})
        if status != 200:
            raise HrApiError(f"{WHERE}: вход не выполнен (HTTP {status}), "
                             "проверьте учётную запись hr_username/hr_password")
        data = self._json(raw, LOGIN_PATH)
        token = data.get("access_token") if isinstance(data, Mapping) else None
        if not isinstance(token, str) or not token:
            raise HrApiError(f"{WHERE}: ответ входа без access_token")
        try:
            ttl = int(data.get("expires_in", _DEFAULT_TTL))
        except (TypeError, ValueError):
            ttl = _DEFAULT_TTL
        self._token = token
        self._expires = self._clock() + max(60, ttl - 60)

    def _authorized(self, path: str) -> tuple[int, bytes]:
        if self._token is None or self._clock() >= self._expires:
            self.login()
        return self._read("GET", path, headers={"Authorization": f"Bearer {self._token}"})

    def get(self, path: str) -> Any:
        status, raw = self._authorized(path)
        if status == 401:  # token muddatidan oldin bekor qilingan — bir marta qayta kirish
            self._token = None
            status, raw = self._authorized(path)
        if status == 401:
            raise HrApiError(f"{WHERE} {path}: доступ запрещён после повторного входа")
        if not 200 <= status < 300:
            raise HrApiError(f"{WHERE} {path}: HTTP {status}")
        return self._json(raw, path)
