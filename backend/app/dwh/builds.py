"""Buildlar: agregatlar snapshot'i. Publish = bitta tranzaksiyada data_version almashtirish;
oxirgi `keep` ta muvaffaqiyatli build saqlanadi (spec 4.7)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.errors import ConflictError
from app.core.logging import get_logger
from app.dwh.aggregates import AGGREGATES

log = get_logger("ugekazna.dwh.builds")

# Fix r1 (I2): `rollback()`ga EXPLICIT berilgan build faqat shu holatlarda qonuniy —
# hech qachon hali publish qilinmagan `ready`ga emas ('ready' faqat ETL'ning o'zi
# `publish()`ni to'g'ridan-to'g'ri chaqirganda, birinchi marta nashr qilish uchun ishlatiladi).
_ROLLBACK_STATUSES = ("published", "superseded")
_PUBLISH_STATUSES = ("ready", *_ROLLBACK_STATUSES)


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
    # Fix r1 (M4): faqat hali qurilayotgan ('building') build tayyor bo'lishi mumkin —
    # allaqachon nashr qilingan/muvaffaqiyatsiz build holatini jimgina qayta yozmaydi.
    conn.execute(text("UPDATE core.builds SET status = 'ready' "
                      "WHERE build_id = :b AND status = 'building'"), {"b": build_id})


def mark_failed(conn: Connection, build_id: int) -> bool:
    """`build_id`ni `failed` deb belgilaydi va uning mart qatorlarini o'chiradi.

    Fix r1 (I1): faqat hali nashr qilinmagan build ('building' yoki 'ready') muvaffaqiyatsiz
    deb belgilanishi mumkin — aks holda (masalan, hozir FAOL/`published` build) bu chaqiruv
    jim no-op bo'ladi (`False` qaytaradi, ogohlantirish loglanadi): faol vitrinani
    "muvaffaqiyatsiz" deb belgilab, uning mart qatorlarini o'chirib qo'yish ishlab chiqarish
    uzilishiga olib keladi. Avval status UPDATE (WHERE bilan qo'riqlangan) bajariladi — u
    muvaffaqiyatli bo'lgandagina mart qatorlari o'chiriladi, shu bilan ikkalasi ham bir xil
    qo'riqlov ostida.
    """
    result = conn.execute(
        text("UPDATE core.builds SET status = 'failed' "
             "WHERE build_id = :b AND status IN ('building', 'ready')"), {"b": build_id})
    if result.rowcount != 1:
        log.warning("mark_failed_denied", build_id=build_id)
        return False
    for aggregate in AGGREGATES:
        # Jadval nomi reyestrdan (whitelist).
        conn.execute(text(f"DELETE FROM mart.{aggregate.table} WHERE build_id = :b"),
                     {"b": build_id})
    return True


def active_build(conn: Connection) -> int | None:
    value = conn.execute(
        text("SELECT active_build_id FROM core.data_version WHERE id = 1")).scalar_one_or_none()
    return None if value is None else int(value)


def publish(conn: Connection, build_id: int, *, keep: int | None) -> None:
    conn.execute(text("SELECT 1 FROM core.data_version WHERE id = 1 FOR UPDATE"))
    status = conn.execute(
        text("SELECT status FROM core.builds WHERE build_id = :b FOR UPDATE"),
        {"b": build_id}).scalar_one_or_none()
    if status not in _PUBLISH_STATUSES:
        raise ConflictError("build_not_available", build_id=build_id)
    conn.execute(text("UPDATE core.builds SET status = 'superseded' "
                      "WHERE status = 'published' AND build_id <> :b"), {"b": build_id})
    conn.execute(text("UPDATE core.builds SET status = 'published', published_at = now() "
                      "WHERE build_id = :b"), {"b": build_id})
    result = conn.execute(
        text("UPDATE core.data_version SET active_build_id = :b, published_at = now() "
             "WHERE id = 1"), {"b": build_id})
    # Fix r1 (M2): `core.data_version` yagona qatori (id=1) migratsiya tomonidan seed
    # qilingan va yuqoridagi FOR UPDATE uni allaqachon qulflagan — shu sabab bu UPDATE har
    # doim aynan 1 qatorga tegishi kerak; aks holda (masalan, qator negadir yo'qolgan bo'lsa)
    # "muvaffaqiyatli publish" deb noto'g'ri signal berish o'rniga xato beramiz.
    if result.rowcount != 1:
        raise ConflictError("build_not_available", build_id=build_id)
    if keep is not None:
        prune(conn, keep)


def prune(conn: Connection, keep: int) -> list[int]:
    """Aktivdan tashqari eng yangi `keep` ta muvaffaqiyatli build qoladi; qolganlari (va
    muvaffaqiyatsizlar) o'chiriladi — mart qatorlari ON DELETE CASCADE bilan ketadi.

    Fix r1 (M6): bundan tashqari, 7 kundan eski `ready`/`building`/`failed` buildlar ham
    (hech qachon nashr qilinmagan yoki bir umr "building"da qolib ketgan — masalan, ETL
    ishchi jarayoni yiqilib, `mark_failed` chaqirilmagan holatlar) — faol build bundan
    mustasno.
    """
    kept = list(conn.execute(
        text("SELECT build_id FROM core.builds WHERE status IN ('published', 'superseded') "
             "ORDER BY build_id DESC LIMIT :k"), {"k": keep}).scalars())
    return list(conn.execute(
        text(
            "DELETE FROM core.builds WHERE build_id IS DISTINCT FROM "
            "(SELECT active_build_id FROM core.data_version WHERE id = 1) AND ("
            "  (status IN ('superseded', 'failed') AND NOT (build_id = ANY(:kept)))"
            "  OR (status IN ('ready', 'building', 'failed') "
            "      AND created_at < now() - interval '7 days')"
            ") RETURNING build_id"
        ), {"kept": kept}).scalars())


def rollback(conn: Connection, build_id: int | None = None) -> int:
    """Aktivdan oldingi (yoki ko'rsatilgan) saqlangan buildga qaytish.

    Fix r1 (M3): `core.data_version` qulfi BIRINCHI olinadi, keyin joriy aktiv build
    o'qiladi, keyin (shu tranzaksiya ichida) `publish()` chaqiriladi — poyga holatisiz
    (concurrent rollback/publish) izchil ko'rinish uchun.
    """
    conn.execute(text("SELECT 1 FROM core.data_version WHERE id = 1 FOR UPDATE"))
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
    else:
        # Fix r1 (I2): EXPLICIT build faqat oldin nashr qilingan bo'lsa qonuniy — hech
        # qachon nashr qilinmagan 'ready' build bu yo'l bilan faollashtirib bo'lmaydi
        # ('ready' faqat ETL'ning bevosita `publish()` chaqiruvi uchun, birinchi nashr).
        status = conn.execute(
            text("SELECT status FROM core.builds WHERE build_id = :b"),
            {"b": target}).scalar_one_or_none()
        if status not in _ROLLBACK_STATUSES:
            raise ConflictError("build_not_available", build_id=target)
    publish(conn, int(target), keep=None)
    return int(target)


def list_builds(conn: Connection) -> list[BuildInfo]:
    active = active_build(conn)
    rows = conn.execute(text(
        "SELECT build_id, created_at, status, load_id, published_at FROM core.builds "
        "ORDER BY build_id DESC LIMIT 50")).all()
    return [BuildInfo(r.build_id, r.created_at, r.status, r.load_id, r.published_at,
                      r.build_id == active) for r in rows]
