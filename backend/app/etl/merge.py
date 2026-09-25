"""stg → dwh (spec 5.2): idempotent upsert (faqat o'zgargan qatorlar), o'lcham kodlari → id,
statyasiz → «Прочие» (+ ogohlantirish), noma'lum filial/o'lcham → etl_error va qator
o'tkazib yuboriladi, oyna ichida to'liq almashtirish, SCD-2 versiyalari.

Barcha identifikatorlar app.dwh.targets reyestridan (whitelist).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from functools import cache

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.dwh import partitions
from app.dwh.targets import DIM_TARGETS, FACT_TARGETS, TARGETS, Lookup, Target
from app.etl.types import Window

ERROR_LIMIT = 1000


@dataclass(frozen=True, slots=True)
class MergeStats:
    target: str
    upserted: int = 0
    deleted: int = 0
    errors: int = 0
    warnings: int = 0


def _lookup_value(i: int, lk: Lookup) -> str:
    if lk.fallback_sql is None:
        return f"l{i}.{lk.column}"
    return (f"coalesce(l{i}.{lk.column}, (SELECT fb.{lk.column} FROM dwh.{lk.dim} fb "
            f"WHERE fb.code = {lk.fallback_sql}))")


def _valid(i: int, lk: Lookup) -> str:
    if lk.fallback_sql is not None:
        return "true"
    if lk.nullable:
        return f"(s.payload->>'{lk.key}' IS NULL OR l{i}.{lk.column} IS NOT NULL)"
    return f"l{i}.{lk.column} IS NOT NULL"


def _updatable(t: Target) -> list[str]:
    data = [*t.columns, *(lk.column for lk in t.lookups)]
    cols = [c for c in data if c not in t.conflict]
    if "src_system" not in t.conflict:
        cols.append("src_system")
    return cols


@cache
def upsert_sql(name: str) -> str:
    t = TARGETS[name]
    insert_cols = [*t.columns, *(lk.column for lk in t.lookups), "src_system", "load_id",
                   "updated_at"]
    exprs = [f"r.{c}" for c in t.columns]
    exprs += [_lookup_value(i, lk) for i, lk in enumerate(t.lookups)]
    exprs += [":source", ":load_id", "now()"]
    joins = "".join(
        f"\nLEFT JOIN dwh.{lk.dim} l{i} ON l{i}.code = s.payload->>'{lk.key}'"
        for i, lk in enumerate(t.lookups)
    )
    conds = ["s.load_id = :load_id", "s.target = :target"]
    conds += [_valid(i, lk) for i, lk in enumerate(t.lookups)]
    if "date_id" in t.columns:
        conds.append("EXISTS (SELECT 1 FROM dwh.dim_date dd WHERE dd.date_id = r.date_id)")
    keys = [f"r.{c}" for c in t.conflict if c != "src_system"]
    updatable = _updatable(t)
    set_list = [f"{c} = EXCLUDED.{c}" for c in updatable]
    set_list += ["load_id = EXCLUDED.load_id", "updated_at = now()"]
    # Shifrmatn har safar boshqacha (tasodifiy nonce) — o'zgarishni blind index bo'yicha aniqlaymiz.
    encrypted = {s.enc_column for s in t.sensitive}
    compared = [c for c in updatable if c not in encrypted]
    old = ", ".join(f"t.{c}" for c in compared)
    new = ", ".join(f"EXCLUDED.{c}" for c in compared)
    return (
        f"INSERT INTO dwh.{t.name} AS t ({', '.join(insert_cols)})\n"
        f"SELECT DISTINCT ON ({', '.join(keys)}) {', '.join(exprs)}\n"
        "FROM stg.rows s\n"
        f"CROSS JOIN LATERAL jsonb_populate_record(NULL::dwh.{t.name}, s.payload) r{joins}\n"
        f"WHERE {' AND '.join(conds)}\n"
        f"ORDER BY {', '.join(keys)}, s.seq DESC\n"
        f"ON CONFLICT ({', '.join(t.conflict)}) DO UPDATE SET {', '.join(set_list)}\n"
        f"WHERE ({old}) IS DISTINCT FROM ({new})"
    )


@cache
def _error_sql(name: str, index: int) -> str:
    lk = TARGETS[name].lookups[index]
    present = f"s.payload->>'{lk.key}' IS NOT NULL" if lk.nullable else "true"
    # `:target` shu so'rovda ikki marta uchraydi (SELECT ro'yxatida va WHERE'da) — Postgres
    # ularni har xil qoidalar bilan tiplaydi (INSERT nishon ustuni vs operator moslashuvi),
    # shuning uchun aniq tur ko'rsatilmasa "text versus character varying" xatosi bilan
    # yiqiladi (AmbiguousParameter). Birinchi uchrashda aniq CAST — ikkinchisi shundan olinadi.
    return (
        "INSERT INTO core.etl_error (run_id, step, severity, target, src_id, code, message)\n"
        f"SELECT :load_id, :step, '{lk.severity}', CAST(:target AS varchar), "
        "left(coalesce(s.payload->>'src_id', s.payload->>'code'), 128), "
        f"'{lk.error_code}', left('Не найден справочник {lk.dim}: ' || "
        f"coalesce(s.payload->>'{lk.key}', '—'), 500)\n"
        f"FROM stg.rows s LEFT JOIN dwh.{lk.dim} d ON d.code = s.payload->>'{lk.key}'\n"
        f"WHERE s.load_id = :load_id AND s.target = :target AND d.{lk.column} IS NULL "
        f"AND {present}\nLIMIT {ERROR_LIMIT}"
    )


_DATE_ERROR_SQL = (
    "INSERT INTO core.etl_error (run_id, step, severity, target, src_id, code, message)\n"
    "SELECT :load_id, :step, 'error', CAST(:target AS varchar), left(s.payload->>'src_id', 128), "
    "'missing_dim', "
    "left('Дата вне справочника dim_date: ' || coalesce(s.payload->>'date_id', '—'), 500)\n"
    "FROM stg.rows s WHERE s.load_id = :load_id AND s.target = :target AND NOT EXISTS "
    "(SELECT 1 FROM dwh.dim_date dd WHERE dd.date_id::text = s.payload->>'date_id')\n"
    f"LIMIT {ERROR_LIMIT}"
)


@cache
def _moved_sql(name: str) -> str:
    # Hujjat sanasi o'zgargan bo'lsa, eski partitsiyadagi nusxani o'chiramiz.
    return (
        f"DELETE FROM dwh.{name} t USING stg.rows s "
        "WHERE s.load_id = :load_id AND s.target = :target AND t.src_system = :source "
        "AND t.doc_type = s.payload->>'doc_type' AND t.src_id = s.payload->>'src_id' "
        "AND t.date_id <> (s.payload->>'date_id')::int"
    )


@cache
def _replace_sql(name: str) -> str:
    return (
        f"DELETE FROM dwh.{name} t WHERE t.src_system = :source "
        "AND t.date_id BETWEEN :from_id AND :to_id AND NOT EXISTS ("
        "SELECT 1 FROM stg.rows s WHERE s.load_id = :load_id AND s.target = :target "
        "AND s.payload->>'src_id' = t.src_id AND s.payload->>'doc_type' = t.doc_type)"
    )


@cache
def _scd_sql(name: str) -> tuple[str, str, str]:
    t = TARGETS[name]
    assert t.scd is not None
    v, k, c = t.scd.table, t.scd.key, t.scd.column
    changed = (f"v.{k} = d.{k} AND v.is_current AND d.load_id = :load_id "
               f"AND v.{c} IS DISTINCT FROM d.{c}")
    same_day = (f"DELETE FROM dwh.{v} v USING dwh.{name} d WHERE {changed} "
                "AND v.valid_from >= CAST(:as_of AS date)")
    close = (f"UPDATE dwh.{v} v SET valid_to = CAST(:as_of AS date) - 1, is_current = false "
             f"FROM dwh.{name} d WHERE {changed}")
    insert = (
        f"INSERT INTO dwh.{v} ({k}, {c}, valid_from, valid_to, is_current) "
        f"SELECT d.{k}, d.{c}, CASE WHEN EXISTS (SELECT 1 FROM dwh.{v} p WHERE p.{k} = d.{k}) "
        "THEN CAST(:as_of AS date) ELSE DATE '2000-01-01' END, NULL, true "
        f"FROM dwh.{name} d WHERE d.load_id = :load_id AND NOT EXISTS "
        f"(SELECT 1 FROM dwh.{v} cur WHERE cur.{k} = d.{k} AND cur.is_current)"
    )
    return same_day, close, insert


def staged_targets(conn: Connection, load_id: int) -> set[str]:
    return set(conn.execute(
        text("SELECT target FROM stg.batch WHERE load_id = :l"), {"l": load_id}).scalars())


def merge_target(conn: Connection, name: str, *, load_id: int, source: str, step: str,
                 as_of: date, window: Window | None = None, replace: bool = False) -> MergeStats:
    t = TARGETS[name]
    params = {"load_id": load_id, "source": source, "target": name, "step": step}
    errors = warnings = deleted = 0
    for i, lk in enumerate(t.lookups):
        count = conn.execute(text(_error_sql(name, i)), params).rowcount
        if lk.fallback_sql:
            warnings += count
        else:
            errors += count
    if "date_id" in t.columns:
        errors += conn.execute(text(_DATE_ERROR_SQL), params).rowcount
    if t.partition is not None:
        deleted += conn.execute(text(_moved_sql(name)), params).rowcount
    upserted = conn.execute(text(upsert_sql(name)), params).rowcount
    if t.scd is not None:
        for sql in _scd_sql(name):
            conn.execute(text(sql), {"load_id": load_id, "as_of": as_of})
    if replace and t.windowed and window is not None:
        deleted += conn.execute(
            text(_replace_sql(name)),
            {**params, "from_id": window.from_id, "to_id": window.to_id},
        ).rowcount
    return MergeStats(name, upserted, deleted, errors, warnings)


def merge_dims(conn: Connection, *, load_id: int, source: str, as_of: date) -> list[MergeStats]:
    staged = staged_targets(conn, load_id)
    return [
        merge_target(conn, name, load_id=load_id, source=source, step="dims", as_of=as_of)
        for name in DIM_TARGETS
        if name in staged
    ]


def merge_facts(conn: Connection, *, load_id: int, source: str, window: Window,
                complete: Collection[str], as_of: date) -> list[MergeStats]:
    staged = staged_targets(conn, load_id)
    out: list[MergeStats] = []
    for name in FACT_TARGETS:
        if name not in staged and name not in complete:
            continue
        if TARGETS[name].partition and name in staged:
            lo, hi = conn.execute(
                text("SELECT min(dd.date), max(dd.date) FROM stg.rows s JOIN dwh.dim_date dd "
                     "ON dd.date_id::text = s.payload->>'date_id' "
                     "WHERE s.load_id = :l AND s.target = :t"),
                {"l": load_id, "t": name},
            ).one()
            if lo is not None:
                partitions.ensure_partitions(conn, name, lo, hi)
        out.append(merge_target(conn, name, load_id=load_id, source=source, step="facts",
                                as_of=as_of, window=window, replace=name in complete))
    return out
