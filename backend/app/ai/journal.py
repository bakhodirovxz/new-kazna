"""AI jurnali = limit reyestri (TZ 7 «Ограничения и журнал», S5 spec 4.4).

Limitlar PostgreSQL'da hisoblanadi (Redis'ga bog'liq emas — Redis tushsa ham cheklov ishlaydi,
fail-closed): so'rov qabul qilinganda advisory lock ostida oxirgi soat (foydalanuvchi) va oxirgi
sutka (tashkilot) yozuvlari sanaladi; oshsa — `AiLimitError` va keyingi urinish vaqti. Qabul
qilingan har so'rov (natijasidan qat'i nazar) limitga kiradi. Savol matni faqat shu jadvalda,
90 kun; audit jurnaliga yozilmaydi.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.audit.service import AuditAction, AuditEvent, record
from app.core.db import get_engine
from app.core.errors import AiLimitError
from app.dwh.reference import current_setting
from app.etl.db import etl_transaction

USER_WINDOW = timedelta(hours=1)
ORG_WINDOW = timedelta(days=1)
RETENTION = timedelta(days=90)
STALE_RUNNING = timedelta(minutes=10)
QUOTA_LOCK = "ugk_ai_quota"


@dataclass(frozen=True, slots=True)
class NewRequest:
    user_id: int
    section: str
    page: str
    filters: dict[str, Any]
    preset: str | None
    question: str | None
    context_chars: int
    provider: str
    model: str


def limits(conn: Connection) -> tuple[int, int]:
    return (int(current_setting(conn, "ai.user_per_hour")),
            int(current_setting(conn, "ai.org_per_day")))


def retry_after(times: Sequence[datetime], limit: int, window: timedelta,
                now: datetime) -> int | None:
    """Oynadagi yozuvlar (o'sish tartibida) limitga yetgan bo'lsa — keyingi ruxsatgacha soniya."""
    if len(times) < limit:
        return None
    expires = times[len(times) - limit] + window
    return max(1, math.ceil((expires - now).total_seconds()))


def _times(conn: Connection, since: datetime, user_id: int | None = None) -> list[datetime]:
    if user_id is None:
        rows = conn.execute(text("SELECT created_at FROM core.ai_requests WHERE created_at > :t "
                                 "ORDER BY created_at"), {"t": since})
    else:
        rows = conn.execute(text("SELECT created_at FROM core.ai_requests WHERE user_id = :u "
                                 "AND created_at > :t ORDER BY created_at"),
                            {"u": user_id, "t": since})
    return list(rows.scalars())


def precheck(user_id: int, now: datetime) -> None:
    """Qimmat kontekst qurishdan OLDIN arzon tekshiruv (qulfsiz); yakuniy tekshiruv `reserve` da."""
    with get_engine("app").connect() as conn:
        per_user, per_org = limits(conn)
        wait = retry_after(_times(conn, now - USER_WINDOW, user_id), per_user, USER_WINDOW, now)
        if wait is not None:
            raise AiLimitError(wait, "user")
        wait = retry_after(_times(conn, now - ORG_WINDOW), per_org, ORG_WINDOW, now)
        if wait is not None:
            raise AiLimitError(wait, "org")


def reserve(req: NewRequest, *, now: datetime) -> int:
    with get_engine("app").begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": QUOTA_LOCK})
        per_user, per_org = limits(conn)
        wait = retry_after(_times(conn, now - USER_WINDOW, req.user_id), per_user, USER_WINDOW,
                           now)
        if wait is not None:
            raise AiLimitError(wait, "user")
        wait = retry_after(_times(conn, now - ORG_WINDOW), per_org, ORG_WINDOW, now)
        if wait is not None:
            raise AiLimitError(wait, "org")
        return int(conn.execute(text(
            "INSERT INTO core.ai_requests (created_at, user_id, section, page, filters, preset, "
            "question, context_chars, provider, model) VALUES (:now, :u, :s, :p, "
            "CAST(:f AS jsonb), :pr, :q, :c, :pv, :m) RETURNING id"),
            {"now": now, "u": req.user_id, "s": req.section, "p": req.page,
             "f": json.dumps(req.filters, ensure_ascii=False), "pr": req.preset,
             "q": req.question, "c": req.context_chars, "pv": req.provider,
             "m": req.model}).scalar_one())


def used_last_hour(conn: Connection, user_id: int, now: datetime) -> int:
    return len(_times(conn, now - USER_WINDOW, user_id))


def finish(request_id: int, *, status: str, error_code: str | None, answer_chars: int,
           duration_ms: int) -> None:
    with get_engine("app").begin() as conn:
        conn.execute(text(
            "UPDATE core.ai_requests SET status = :st, error_code = :e, answer_chars = :a, "
            "duration_ms = :d, finished_at = now() WHERE id = :i AND status = 'running'"),
            {"st": status, "e": error_code, "a": answer_chars, "d": duration_ms,
             "i": request_id})


def purge(now: datetime) -> tuple[int, int]:
    """Worker (ugk_etl): 90 kundan eski yozuvlar o'chiriladi, osilib qolgan `running` yopiladi."""
    with etl_transaction() as conn:
        stale = conn.execute(text(
            "UPDATE core.ai_requests SET status = 'error', error_code = 'stale', "
            "finished_at = :now WHERE status = 'running' AND created_at < :t"),
            {"now": now, "t": now - STALE_RUNNING}).rowcount
        deleted = conn.execute(text("DELETE FROM core.ai_requests WHERE created_at < :t"),
                               {"t": now - RETENTION}).rowcount
    if deleted or stale:
        record(AuditEvent(action=AuditAction.AI_JOURNAL_PURGED, object_type="ai_requests",
                          details={"deleted": deleted, "stale": stale,
                                   "retention_days": RETENTION.days}), role="etl")
    return deleted, stale
