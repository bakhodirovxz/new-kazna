"""cbu.uz JSON arxivi mijozi: GET /ru/arkhiv-kursov-valyut/json/all/<YYYY-MM-DD>/.

Javob: [{"Ccy": "USD", "Nominal": "1", "Rate": "11830.87", "Date": "25.09.2026", …}] (2026-09-25 da
tekshirilgan). Vaqtinchalik xatolar (tarmoq, tayм-aut, 5xx, 429) → ConnectorUnavailableError
(runner qayta urinadi); format/4xx/redirect → CbuError (qayta urinilmaydi).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

import httpx
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from app.etl.types import ConnectorUnavailableError

RATES_PATH = "/ru/arkhiv-kursov-valyut/json/all/{day}/"
TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
MAX_BYTES = 1024 * 1024
_RATE_RE = re.compile(r"^\d{1,12}(\.\d{1,8})?$")
_DAY_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_SIX = Decimal("0.000001")


class CbuError(ValueError):
    """Qayta urinilmaydigan ЦБ javob xatosi."""


def _rate(value: Any) -> Decimal:
    if isinstance(value, str) and _RATE_RE.fullmatch(value) and Decimal(value) > 0:
        return Decimal(value)
    raise ValueError("Rate: musbat son satri kerak (nuqta bilan)")


def _nominal(value: Any) -> int:
    if isinstance(value, str | int) and not isinstance(value, bool) \
            and re.fullmatch(r"\d{1,6}", str(value)) and int(value) >= 1:
        return int(value)
    raise ValueError("Nominal: musbat butun son kerak")


def _day(value: Any) -> date:
    if isinstance(value, str) and _DAY_RE.fullmatch(value):
        return datetime.strptime(value, "%d.%m.%Y").replace(tzinfo=UTC).date()
    raise ValueError("Date: ДД.ММ.ГГГГ kerak")


class CbuRate(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    ccy: Annotated[str, Field(alias="Ccy", pattern=r"^[A-Z]{3}$")]
    rate: Annotated[Decimal, BeforeValidator(_rate), Field(alias="Rate")]
    nominal: Annotated[int, BeforeValidator(_nominal), Field(alias="Nominal")]
    day: Annotated[date, BeforeValidator(_day), Field(alias="Date")]

    @property
    def per_unit(self) -> Decimal:
        """1 birlik valyuta uchun so'm (dwh.fx_rate.rate)."""
        return (self.rate / self.nominal).quantize(_SIX)


_RATES = TypeAdapter(list[CbuRate])


class CbuClient:
    def __init__(self, base_url: str = "https://cbu.uz", *, proxy: str = "",
                 transport: httpx.BaseTransport | None = None,
                 timeout: httpx.Timeout = TIMEOUT, max_bytes: int = MAX_BYTES) -> None:
        self.max_bytes = max_bytes
        self.http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, verify=True, trust_env=False,
            follow_redirects=False, proxy=proxy or None, transport=transport,
            headers={"Accept": "application/json"})

    def close(self) -> None:
        self.http.close()

    def rates(self, day: date) -> list[CbuRate]:
        path = RATES_PATH.format(day=day.isoformat())
        where = f"ЦБ {day:%d.%m.%Y}"
        chunks: list[bytes] = []
        size = 0
        try:
            with self.http.stream("GET", path) as response:
                status = response.status_code
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise CbuError(f"{where}: ответ больше {self.max_bytes} байт")
                    chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise ConnectorUnavailableError(f"{where}: тайм-аут") from exc
        except httpx.TransportError as exc:
            raise ConnectorUnavailableError(f"{where}: {type(exc).__name__}") from exc
        if status >= 500 or status == 429:
            raise ConnectorUnavailableError(f"{where}: HTTP {status}")
        if status != 200:
            raise CbuError(f"{where}: HTTP {status}")
        try:
            data = json.loads(b"".join(chunks).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CbuError(f"{where}: ответ не JSON") from exc
        try:
            return _RATES.validate_python(data)
        except PydanticValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            raise CbuError(f"{where}: неожиданная структура ответа ({loc} — {first['msg']})") \
                from exc


def cbu_probe(client_factory: Callable[[], CbuClient] | None = None) -> str:
    """Bugungi kurslar so'rovi -> faqat xavfsiz kod (U8). Sozlama o'chiq - `not_configured`."""
    from app.core import sysconfig
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.dwh.dates import today_tashkent

    with get_engine("app").connect() as conn:
        if not sysconfig.current(conn, "cbu.enabled"):
            return "not_configured"
    settings = get_settings()
    client = client_factory() if client_factory else CbuClient(
        settings.cbu_base_url, proxy=settings.egress_proxy)
    try:
        client.rates(today_tashkent())
    except ConnectorUnavailableError as exc:
        return "timeout" if "тайм-аут" in str(exc) else "connect_failed"
    except CbuError as exc:
        return "http_error" if "HTTP" in str(exc) else "format_error"
    finally:
        client.close()
    return "ok"
