"""Davriy xizmat vazifalari — CLI (`python -m app.cli`) va worker ikkalasi ishlatadi."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, or_, text

from app.auth.models import MfaChallenge, UserSession
from app.core.db import new_session
from app.etl.db import etl_transaction


def cleanup_sessions(now: datetime | None = None) -> tuple[int, int]:
    """Eskirgan 2FA challenge (1 kun) va sessiyalar (30 kun) — (challenge, sessiya) soni."""
    now = now or datetime.now(UTC)
    with new_session() as db:
        challenges = cast(CursorResult[Any], db.execute(
            delete(MfaChallenge).where(MfaChallenge.expires_at < now - timedelta(days=1))
        )).rowcount
        old = now - timedelta(days=30)
        stale = cast(CursorResult[Any], db.execute(
            delete(UserSession).where(
                or_(UserSession.absolute_expires_at < old, UserSession.revoked_at < old))
        )).rowcount
        db.commit()
    return challenges, stale


def cleanup_staging(days: int = 7) -> int:
    """`days` kundan eski (yoki jurnalda yo'q) yuklashlarning staging qatorlari."""
    with etl_transaction() as conn:
        removed = conn.execute(text(
            "DELETE FROM stg.rows r WHERE NOT EXISTS (SELECT 1 FROM core.etl_run e "
            "WHERE e.id = r.load_id AND e.started_at > now() - make_interval(days => :d))"),
            {"d": days}).rowcount
        conn.execute(text(
            "DELETE FROM stg.batch b WHERE NOT EXISTS (SELECT 1 FROM core.etl_run e "
            "WHERE e.id = b.load_id AND e.started_at > now() - make_interval(days => :d))"),
            {"d": days})
    return int(removed)
