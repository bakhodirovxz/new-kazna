"""Jonli quvvat (treplex.uz, eski dashboard: GET /api/cascades/ges, auth yo'q) — «Текущая мощность»
(S3 spec 3.2). Javob:
{date, cascades:[{name, "all-power", "all-agg", stations:[{ges, power, agg}]}]};
power — MVt (son yoki satr), agg — "ishda/zaxira/ta'mir". Bu kunlik energiya EMAS.

Runner/build'siz (qaror 4): har so'rovning moslashtirilgan stansiyalari bitta snap_at (UTC,
daqiqagacha) bilan dwh.fact_power_snapshot ga; manba ishlamasa oxirgi snapshot saqlanadi.
Tarmoq: faqat worker, https, trust_env=False, redirect yo'q, ≤ 1 MiB, ixtiyoriy EGRESS_PROXY.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core import sysconfig
from app.core.config import ConfigError, Settings
from app.core.db import get_engine
from app.core.logging import get_logger
from app.etl.askue.registry import AskueStation, normalize_name
from app.etl.db import etl_transaction
from app.etl.types import ConnectorUnavailableError

TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)
MAX_BYTES = 1024 * 1024
DEADLINE = 60.0  # s: butun so'rov uchun devor soati (sekin-tomchi serverdan himoya)
_POWER = re.compile(r"^\d{1,5}(\.\d{1,4})?$")
_AGG = re.compile(r"^\d{1,3}/\d{1,3}/\d{1,3}$")
WHERE = "АСКУЭ (онлайн)"
log = get_logger("ugekazna.askue.live")


class LiveError(ValueError):
    """Qayta urinilmaydigan jonli manba xatosi (format, 4xx, redirect, hajm)."""


def _power(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("power: son kerak")
    if isinstance(value, int | float | Decimal):
        raw = str(value)
    elif isinstance(value, str):
        raw = value.strip().replace(",", ".")
    else:
        raise ValueError("power: son kerak")
    if not _POWER.fullmatch(raw):
        raise ValueError("power: 0…99999 MVt")
    return Decimal(raw)


def _agg(value: Any) -> tuple[int, int, int]:
    if value is None or value == "":
        return (0, 0, 0)
    if not isinstance(value, str) or not _AGG.fullmatch(value.strip()):
        raise ValueError("agg: «ishda/zaxira/ta'mir» kerak")
    working, reserve, repair = (int(x) for x in value.strip().split("/"))
    return (working, reserve, repair)


class LiveStation(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    ges: Annotated[str, Field(min_length=1, max_length=200)]
    power: Annotated[Decimal, BeforeValidator(_power)]
    agg: Annotated[tuple[int, int, int], BeforeValidator(_agg)] = (0, 0, 0)


class LiveCascade(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    stations: list[LiveStation]


class LiveResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    date: Annotated[str | None, Field(max_length=40)] = None
    cascades: list[LiveCascade]


class GesLiveClient:
    def __init__(self, url: str, *, proxy: str = "",
                 transport: httpx.BaseTransport | None = None, timeout: httpx.Timeout = TIMEOUT,
                 max_bytes: int = MAX_BYTES) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigError("askue.live_url https:// manzil bo'lishi kerak")
        self.url = url
        self.max_bytes = max_bytes
        self.http = httpx.Client(timeout=timeout, verify=True, trust_env=False,
                                 follow_redirects=False, proxy=proxy or None, transport=transport,
                                 headers={"Accept": "application/json"})

    def close(self) -> None:
        self.http.close()

    def fetch(self) -> LiveResponse:
        chunks: list[bytes] = []
        size = 0
        deadline = time.monotonic() + DEADLINE
        try:
            with self.http.stream("GET", self.url) as response:
                status = response.status_code
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise ConnectorUnavailableError(f"{WHERE}: тайм-аут")
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise LiveError(f"{WHERE}: ответ больше {self.max_bytes} байт")
                    chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise ConnectorUnavailableError(f"{WHERE}: тайм-аут") from exc
        except httpx.TransportError as exc:
            raise ConnectorUnavailableError(f"{WHERE}: {type(exc).__name__}") from exc
        except httpx.HTTPError as exc:  # masalan DecodingError: qayta urinilmaydi
            raise LiveError(f"{WHERE}: {type(exc).__name__}") from exc
        if status >= 500 or status == 429:
            raise ConnectorUnavailableError(f"{WHERE}: HTTP {status}")
        if status != 200:
            raise LiveError(f"{WHERE}: HTTP {status}")
        try:
            data = json.loads(b"".join(chunks).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LiveError(f"{WHERE}: ответ не JSON") from exc
        try:
            return LiveResponse.model_validate(data)
        except PydanticValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            raise LiveError(f"{WHERE}: неожиданная структура ответа ({loc} — {first['msg']})") \
                from exc


@dataclass(frozen=True, slots=True)
class Snapshot:
    station: str  # AskueStation.code
    station_name: str
    cascade_name: str
    branch_code: str
    power_mw: Decimal
    units_working: int
    units_reserve: int
    units_repair: int


def map_snapshot(resp: LiveResponse,
                 stations: list[AskueStation]) -> tuple[list[Snapshot], list[str]]:
    by_name = {normalize_name(s.name): s for s in stations}
    out: list[Snapshot] = []
    unmapped: list[str] = []
    seen: set[str] = set()
    for cascade in resp.cascades:
        for item in cascade.stations:
            key = normalize_name(item.ges)
            station = by_name.get(key)
            if station is None:
                unmapped.append(item.ges.strip()[:200])
                continue
            if key in seen:
                continue
            seen.add(key)
            working, reserve, repair = item.agg
            out.append(Snapshot(station.code, item.ges.strip()[:200], cascade.name.strip()[:200],
                                station.branch_code, item.power, working, reserve, repair))
    return out, unmapped


def store(conn: Connection, snap_at: datetime, source_date: str | None,
          snaps: list[Snapshot]) -> int:
    ids: dict[str, int] = {r.code: r.branch_id for r in conn.execute(
        text("SELECT code, branch_id FROM dwh.dim_branch WHERE code = ANY(:c)"),
        {"c": [s.branch_code for s in snaps] or [""]})}
    stored = 0
    for s in snaps:
        branch_id = ids.get(s.branch_code)
        if branch_id is None:
            log.warning("askue_live_unknown_branch", branch=s.branch_code, station=s.station)
            continue
        conn.execute(text(
            "INSERT INTO dwh.fact_power_snapshot (snap_at, station, station_name, cascade_name, "
            "branch_id, power_mw, units_working, units_reserve, units_repair, source_date) "
            "VALUES (:t, :st, :sn, :cn, :b, :p, :w, :r, :x, :d) "
            "ON CONFLICT (station, snap_at) DO UPDATE SET power_mw = EXCLUDED.power_mw, "
            "units_working = EXCLUDED.units_working, units_reserve = EXCLUDED.units_reserve, "
            "units_repair = EXCLUDED.units_repair, source_date = EXCLUDED.source_date, "
            "loaded_at = now()"),
            {"t": snap_at, "st": s.station, "sn": s.station_name, "cn": s.cascade_name,
             "b": branch_id, "p": s.power_mw, "w": s.units_working, "r": s.units_reserve,
             "x": s.units_repair, "d": source_date})
        stored += 1
    return stored


def prune(conn: Connection, now: datetime, keep_days: int) -> int:
    return conn.execute(text("DELETE FROM dwh.fact_power_snapshot WHERE snap_at < :cut"),
                        {"cut": now - timedelta(days=keep_days)}).rowcount


@dataclass(frozen=True, slots=True)
class PollResult:
    snap_at: datetime
    stored: int
    unmapped: list[str]
    pruned: int


def poll_power(settings: Settings, *, client: GesLiveClient | None = None,
               now: datetime | None = None) -> PollResult:
    moment = (now or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
    with etl_transaction() as conn:
        stations = [AskueStation.model_validate(s)
                    for s in sysconfig.current(conn, "askue.stations")]
        keep = int(sysconfig.current(conn, "askue.live_keep_days"))
        url = str(sysconfig.current(conn, "askue.live_url"))
    own = client is None
    live_client = client or GesLiveClient(url, proxy=settings.egress_proxy)
    try:
        resp = live_client.fetch()
    finally:
        if own:
            live_client.close()
    snaps, unmapped = map_snapshot(resp, stations)
    if unmapped:
        log.warning("askue_live_unmapped", count=len(unmapped),
                    names=[repr(n) for n in unmapped[:10]])
    with etl_transaction() as conn:
        stored = store(conn, moment, resp.date, snaps)
        pruned = prune(conn, moment, keep)
    return PollResult(moment, stored, unmapped, pruned)


def poll_power_job(settings: Settings) -> None:
    """Worker jobi: xato ko'tarilmaydi (keyingi so'rov 10 daqiqadan keyin), snapshot qoladi."""
    with get_engine("app").connect() as conn:
        url = str(sysconfig.current(conn, "askue.live_url"))
    if not url:  # U5: job shartsiz qo'shiladi, manba sozlanmagan bo'lsa o'tkazib yuboradi
        log.info("askue_live_skipped", reason="not_configured")
        return
    try:
        result = poll_power(settings)
    except ConnectorUnavailableError as exc:
        log.warning("askue_live_unavailable", error=str(exc))
        return
    except (LiveError, ConfigError) as exc:
        log.error("askue_live_failed", error=str(exc))
        return
    log.info("askue_live_polled", stored=result.stored, unmapped=len(result.unmapped),
             pruned=result.pruned)


def askue_live_check_command(settings: Settings, out: Callable[[str], None], *,
                             client: GesLiveClient | None = None) -> int:
    """Operator tekshiruvi: manba javobi va askue.stations bilan moslashtirish (yozuvsiz)."""
    with get_engine("app").connect() as conn:
        url = str(sysconfig.current(conn, "askue.live_url"))
    if client is None and not url:
        out("askue.live_url berilmagan (Администрирование → Интеграции) — jonli quvvat o'chiq")
        return 2
    try:
        live_client = client or GesLiveClient(url, proxy=settings.egress_proxy)
    except ConfigError as exc:
        out(f"Konfiguratsiya xatosi: {exc}")
        return 2
    try:
        resp = live_client.fetch()
    except (ConnectorUnavailableError, LiveError) as exc:
        out(f"XATO: {exc}")
        return 1
    finally:
        if client is None:
            live_client.close()
    with get_engine("app").connect() as conn:
        stations = [AskueStation.model_validate(s)
                    for s in sysconfig.current(conn, "askue.stations")]
    snaps, unmapped = map_snapshot(resp, stations)
    for s in snaps:
        out(f"OK   {s.station:<20} {s.branch_code:<10} {s.power_mw} МВт  {s.station_name}")
    for name in unmapped:
        out(f"---  {name} (askue.stations'da yo'q)")
    out(f"Stansiyalar: {len(snaps)} moslashtirilgan, {len(unmapped)} moslashtirilmagan; "
        f"manba sanasi: {resp.date or '—'}")
    return 0
