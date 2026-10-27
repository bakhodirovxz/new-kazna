"""Operator CLI: АСКУЭ stansiyalari ↔ filiallar moslashtirishi (`askue.stations`).

Stansiya faqat ГЭС/kaskad filialiga bog'lanadi (HQ — yo'q). Yangi versiya + audit (via=cli).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import text

from app.admin.config_service import write_setting
from app.audit.service import AuditAction, AuditEvent, record
from app.core.db import get_engine, new_session
from app.dwh.reference import current_setting, validate_setting
from app.etl.askue.registry import STATION_KINDS
from app.etl.db import etl_transaction

Out = Callable[[str], None]


def _show(stations: list[dict[str, str]], out: Out) -> None:
    for s in stations:
        out(f"{s['code']:<20} {s['branch_code']:<10} {s['name']}")


def askue_stations_command(file: Path | None, out: Out) -> int:
    if file is None:
        with get_engine("app").connect() as conn:
            current = list(current_setting(conn, "askue.stations"))
        _show(current, out)
        out(f"askue.stations: {len(current)} ta stansiya")
        return 0
    try:
        value = validate_setting("askue.stations", json.loads(file.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        out(f"Xato: {exc}")
        return 1
    with etl_transaction() as conn:
        kinds: dict[str, str] = {r.code: r.kind for r in conn.execute(
            text("SELECT code, kind FROM dwh.dim_branch"))}
    missing = sorted({s["branch_code"] for s in value} - set(kinds))
    if missing:
        out(f"Xato: noma'lum filial kodlari: {', '.join(missing)}")
        return 1
    not_station = sorted({s["branch_code"] for s in value if kinds[s["branch_code"]]
                          not in STATION_KINDS})
    if not_station:
        out(f"Xato: stansiya emas (kind ≠ ges/cascade): {', '.join(not_station)}")
        return 1
    with new_session() as db:
        version, _before = write_setting(db, "askue.stations", value, None)
        db.commit()
    if version is None:
        out("askue.stations: o'zgarish yo'q")
        _show(value, out)
        return 0
    record(AuditEvent(action=AuditAction.SETTING_UPDATED, object_type="setting",
                      object_id="askue.stations",
                      details={"via": "cli", "version": version, "stations": len(value)}))
    _show(value, out)
    out(f"askue.stations: versiya {version}, {len(value)} ta stansiya")
    return 0
