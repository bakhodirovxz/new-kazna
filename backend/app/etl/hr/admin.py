"""Operator CLI: HR tashkilotlari ↔ filiallar moslashtirishi (`hr.orgs`). Yangi versiya + audit."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import text

from app.admin.config_service import write_setting
from app.audit.service import AuditAction, AuditEvent, record
from app.core.db import get_engine, new_session
from app.dwh.reference import current_setting, validate_setting
from app.etl.db import etl_transaction

Out = Callable[[str], None]


def _show(orgs: list[dict[str, str]], out: Out) -> None:
    for o in orgs:
        out(f"{o['branch_code']:<10} {o['org']}")


def hr_orgs_command(file: Path | None, out: Out) -> int:
    if file is None:
        with get_engine("app").connect() as conn:
            current = list(current_setting(conn, "hr.orgs"))
        _show(current, out)
        out(f"hr.orgs: {len(current)} ta tashkilot")
        return 0
    try:
        value = validate_setting("hr.orgs", json.loads(file.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        out(f"Xato: {exc}")
        return 1
    with etl_transaction() as conn:
        known = set(conn.execute(text("SELECT code FROM dwh.dim_branch")).scalars())
    missing = sorted({o["branch_code"] for o in value} - known)
    if missing:
        out(f"Xato: noma'lum filial kodlari: {', '.join(missing)}")
        return 1
    with new_session() as db:
        version, _before = write_setting(db, "hr.orgs", value, None)
        db.commit()
    version = version or 0
    record(AuditEvent(action=AuditAction.SETTING_UPDATED, object_type="setting",
                      object_id="hr.orgs",
                      details={"via": "cli", "version": version, "orgs": len(value)}))
    _show(value, out)
    out(f"hr.orgs: versiya {version}, {len(value)} ta tashkilot")
    return 0
