"""Ma'lumot yangiligi (TZ 6 «Состояния», 9 «Мониторинг»): oxirgi muvaffaqiyatli yuklash."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.dwh.reference import current_setting


@dataclass(frozen=True, slots=True)
class Freshness:
    last_success_at: datetime | None
    stale: bool
    max_age_hours: int
    active_build_id: int | None


def freshness(conn: Connection, now: datetime) -> Freshness:
    last = conn.execute(
        text("SELECT max(finished_at) FROM core.etl_run WHERE status = 'success'")
    ).scalar_one_or_none()
    active = conn.execute(
        text("SELECT active_build_id FROM core.data_version WHERE id = 1")
    ).scalar_one_or_none()
    max_age = int(current_setting(conn, "freshness.max_age_hours"))
    stale = last is None or now - last > timedelta(hours=max_age)
    return Freshness(last, stale, max_age, None if active is None else int(active))
