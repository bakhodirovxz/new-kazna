"""Buildlar: agregatlar snapshot'i. Publish = bitta tranzaksiyada data_version almashtirish;
oxirgi `keep` ta muvaffaqiyatli build saqlanadi (spec 4.7)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.errors import ConflictError
from app.dwh.aggregates import AGGREGATES


@dataclass(frozen=True, slots=True)
class BuildInfo:
    build_id: int
    created_at: datetime
    status: str
    load_id: int | None
    published_at: datetime | None
    active: bool


def create_build(conn: Connection, load_id: int | None) -> int:
    return int(conn.execute(
        text("INSERT INTO core.builds (status, load_id) VALUES ('building', :l) "
             "RETURNING build_id"), {"l": load_id}).scalar_one())


def mark_ready(conn: Connection, build_id: int) -> None:
    conn.execute(text("UPDATE core.builds SET status = 'ready' WHERE build_id = :b"),
                 {"b": build_id})


def mark_failed(conn: Connection, build_id: int) -> None:
    for aggregate in AGGREGATES:
        # Jadval nomi reyestrdan (whitelist).
        conn.execute(text(f"DELETE FROM mart.{aggregate.table} WHERE build_id = :b"),
                     {"b": build_id})
    conn.execute(text("UPDATE core.builds SET status = 'failed' WHERE build_id = :b"),
                 {"b": build_id})


def active_build(conn: Connection) -> int | None:
    value = conn.execute(
        text("SELECT active_build_id FROM core.data_version WHERE id = 1")).scalar_one_or_none()
    return None if value is None else int(value)


def publish(conn: Connection, build_id: int, *, keep: int | None) -> None:
    conn.execute(text("SELECT 1 FROM core.data_version WHERE id = 1 FOR UPDATE"))
    status = conn.execute(
        text("SELECT status FROM core.builds WHERE build_id = :b FOR UPDATE"),
        {"b": build_id}).scalar_one_or_none()
    if status not in ("ready", "published", "superseded"):
        raise ConflictError("build_not_available", build_id=build_id)
    conn.execute(text("UPDATE core.builds SET status = 'superseded' "
                      "WHERE status = 'published' AND build_id <> :b"), {"b": build_id})
    conn.execute(text("UPDATE core.builds SET status = 'published', published_at = now() "
                      "WHERE build_id = :b"), {"b": build_id})
    conn.execute(text("UPDATE core.data_version SET active_build_id = :b, published_at = now() "
                      "WHERE id = 1"), {"b": build_id})
    if keep is not None:
        prune(conn, keep)


def prune(conn: Connection, keep: int) -> list[int]:
    """Aktivdan tashqari eng yangi `keep` ta muvaffaqiyatli build qoladi; qolganlari (va
    muvaffaqiyatsizlar) o'chiriladi — mart qatorlari ON DELETE CASCADE bilan ketadi."""
    kept = list(conn.execute(
        text("SELECT build_id FROM core.builds WHERE status IN ('published', 'superseded') "
             "ORDER BY build_id DESC LIMIT :k"), {"k": keep}).scalars())
    return list(conn.execute(
        text("DELETE FROM core.builds WHERE status IN ('superseded', 'failed') "
             "AND NOT (build_id = ANY(:kept)) AND build_id IS DISTINCT FROM "
             "(SELECT active_build_id FROM core.data_version WHERE id = 1) "
             "RETURNING build_id"), {"kept": kept}).scalars())


def rollback(conn: Connection, build_id: int | None = None) -> int:
    """Aktivdan oldingi (yoki ko'rsatilgan) saqlangan buildga qaytish."""
    current = active_build(conn)
    target = build_id
    if target is None:
        if current is None:
            raise ConflictError("build_not_available")
        target = conn.execute(
            text("SELECT build_id FROM core.builds WHERE status = 'superseded' "
                 "AND build_id < :a ORDER BY build_id DESC LIMIT 1"),
            {"a": current}).scalar_one_or_none()
        if target is None:
            raise ConflictError("build_not_available")
    publish(conn, int(target), keep=None)
    return int(target)


def list_builds(conn: Connection) -> list[BuildInfo]:
    active = active_build(conn)
    rows = conn.execute(text(
        "SELECT build_id, created_at, status, load_id, published_at FROM core.builds "
        "ORDER BY build_id DESC LIMIT 50")).all()
    return [BuildInfo(r.build_id, r.created_at, r.status, r.load_id, r.published_at,
                      r.build_id == active) for r in rows]
