"""stg → dwh (spec 5.2): idempotent upsert (faqat o'zgargan qatorlar), o'lcham kodlari → id,
statyasiz → «Прочие» (+ ogohlantirish), noma'lum filial/o'lcham → etl_error va qator
o'tkazib yuboriladi, oyna ichida to'liq almashtirish, SCD-2 versiyalari.

Barcha identifikatorlar app.dwh.targets reyestridan (whitelist).

Qator darajasidagi nosozliklar (fix r1, I3) butun yuklashni to'xtatmaydi: har bir staging
qatori `dwh.{target}` ustunlariga solishtirib PG16 `pg_input_is_valid()` bilan oldindan
tekshiriladi (int/date/numeric/varchar uzunligi — hammasi bitta mexanizm, ampirik tekshirildi:
`pg_input_is_valid` varchar(n) uzunligini ham, numeric aniqlik/shkala chegarasini ham to'g'ri
rad etadi). Faqat TO'LIQ tur-to'g'ri qatorlar `jsonb_populate_record`ga uzatiladi — aks holda
noto'g'ri matn (masalan, "abc"::numeric) butun tranzaksiyani yiqitardi. Tur xatosi topilgan
qator `core.etl_error`ga `invalid_type` kodi va maydon nomi bilan yoziladi (QIYMATSIZ — sezgir
maydonlar STAGING'GA umuman tushmaydi, boshqalari uchun ham qiymat log/xabarga chiqarilmaydi)
va upsert'dan chetlatiladi. CHECK (>= 0) bilan himoyalangan ustunlar (jadval katalogidan
avtomatik aniqlanadi) manfiy bo'lsa — `negative_amount` xatosi, xuddi shunday chetlatiladi.
"""

from __future__ import annotations

import re
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


@dataclass(frozen=True, slots=True)
class ColumnMeta:
    pg_type: str  # format_type() natijasi — pg_input_is_valid()ga uzatiladi
    default_sql: str | None  # ustun DEFAULT ifodasi (masalan "0"), yo'q bo'lsa None
    nonneg: bool  # jadvalda shu ustun uchun CHECK (col >= 0) mavjudmi


_META_CACHE: dict[str, dict[str, ColumnMeta]] = {}
_NONNEG_RE_TEMPLATE = r"\b{}\b\s*>=\s*\(?0\)?"


def _table_meta(conn: Connection, table: str) -> dict[str, ColumnMeta]:
    """`dwh.{table}` ustunlari haqida katalog ma'lumoti — bir marta so'raladi, keyin keshdan
    (sxema jarayon davomida o'zgarmaydi). `ugk_etl`ning pg_catalog'ni o'qishga cheklovi yo'q."""
    cached = _META_CACHE.get(table)
    if cached is not None:
        return cached
    cols = conn.execute(
        text(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod), "
            "pg_get_expr(d.adbin, d.adrelid) "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
            "WHERE n.nspname = 'dwh' AND c.relname = :t AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"t": table},
    ).all()
    checks = conn.execute(
        text(
            "SELECT a.attname, pg_get_constraintdef(co.oid) "
            "FROM pg_constraint co "
            "JOIN unnest(co.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
            "JOIN pg_attribute a ON a.attrelid = co.conrelid AND a.attnum = k.attnum "
            "WHERE co.conrelid = to_regclass('dwh.' || :t) AND co.contype = 'c'"
        ),
        {"t": table},
    ).all()
    nonneg = {
        name
        for name, definition in checks
        if re.search(_NONNEG_RE_TEMPLATE.format(re.escape(name)), definition)
    }
    meta = {
        name: ColumnMeta(pg_type, default_sql, name in nonneg)
        for name, pg_type, default_sql in cols
    }
    _META_CACHE[table] = meta
    return meta


def _type_ok_expr(col: str, pg_type: str) -> str:
    escaped = pg_type.replace("'", "''")
    return f"(s.payload->>'{col}' IS NULL OR pg_input_is_valid(s.payload->>'{col}', '{escaped}'))"


def _dedupe_keys(t: Target) -> list[str]:
    # Fix r1, I2: partitsiyalangan faktlarda bitta partiyada bir xil hujjat turli sanada
    # ikki marta kelsa, `date_id`ni HISOBGA OLMAY (doc_type, src_id) bo'yicha dublikat olib
    # tashlanadi — oxirgisi (`seq` bo'yicha) g'olib. Boshqa maqsadlarda (jumladan fx_rate,
    # unda date_id tabiiy kalitning bir qismi) tabiiy kalit o'zgarishsiz qoladi.
    if t.partition is not None:
        return ["doc_type", "src_id"]
    return [c for c in t.conflict if c != "src_system"]


def _staged_cte_sql(conn: Connection, name: str) -> str:
    """`candidate` (tur-to'g'ri xom qatorlar) → `populated` (jsonb_populate_record, xavfsiz —
    faqat tur-to'g'ri qatorlarga qo'llanadi) → `deduped` (partiya ichi dublikat, fix r1 I2)."""
    t = TARGETS[name]
    meta = _table_meta(conn, name)
    checks = " AND ".join(_type_ok_expr(c, meta[c].pg_type) for c in t.columns)
    where_extra = f" AND {checks}" if checks else ""
    cols = ", ".join(f"r.{c}" for c in t.columns)
    keys = _dedupe_keys(t)
    return (
        "candidate AS (\n"
        "  SELECT s.seq, s.payload FROM stg.rows s\n"
        f"  WHERE s.load_id = :load_id AND s.target = :target{where_extra}\n"
        "),\n"
        "populated AS (\n"
        f"  SELECT c.seq, c.payload, {cols}\n"
        "  FROM candidate c\n"
        f"  CROSS JOIN LATERAL jsonb_populate_record(NULL::dwh.{name}, c.payload) r\n"
        "),\n"
        "deduped AS (\n"
        f"  SELECT DISTINCT ON ({', '.join(keys)}) *\n"
        "  FROM populated\n"
        f"  ORDER BY {', '.join(keys)}, seq DESC\n"
        ")"
    )


def _lookup_value(i: int, lk: Lookup) -> str:
    if lk.fallback_sql is None:
        return f"l{i}.{lk.column}"
    return (f"coalesce(l{i}.{lk.column}, (SELECT fb.{lk.column} FROM dwh.{lk.dim} fb "
            f"WHERE fb.code = {lk.fallback_sql}))")


def _valid(i: int, lk: Lookup) -> str:
    # Fix r1, M2: bo'sh satr NULL kabi ko'riladi — bo'lmasa '' hech qanday kod bilan mos
    # kelmagani uchun "topilmadi" bo'lib qolardi, nullable lookup'da esa "berilmagan" deb
    # hisoblanishi kerak.
    key_expr = f"NULLIF(s.payload->>'{lk.key}', '')"
    if lk.fallback_sql is not None:
        return "true"
    if lk.nullable:
        return f"({key_expr} IS NULL OR l{i}.{lk.column} IS NOT NULL)"
    return f"l{i}.{lk.column} IS NOT NULL"


def _updatable(t: Target) -> list[str]:
    data = [*t.columns, *(lk.column for lk in t.lookups)]
    cols = [c for c in data if c not in t.conflict]
    if "src_system" not in t.conflict:
        cols.append("src_system")
    return cols


def _with_insertable(conn: Connection, name: str) -> str:
    """`insertable` — lookup'lari yechilgan, sana/manfiylik tekshiruvidan o'tgan, tayyor
    qatorlar. `upsert_sql` va `_moved_sql` ikkalasi ham shu bitta ro'yxatdan foydalanadi
    (fix r1, M1: ko'chgan hujjat eski nusxasi faqat yangi qator haqiqatan qabul qilinganda
    o'chiriladi)."""
    t = TARGETS[name]
    meta = _table_meta(conn, name)
    cte = _staged_cte_sql(conn, name)
    joins = "".join(
        f"\nLEFT JOIN dwh.{lk.dim} l{i} ON l{i}.code = NULLIF(s.payload->>'{lk.key}', '')"
        for i, lk in enumerate(t.lookups)
    )
    conds = [_valid(i, lk) for i, lk in enumerate(t.lookups)]
    if "date_id" in t.columns:
        conds.append("EXISTS (SELECT 1 FROM dwh.dim_date x WHERE x.date_id = s.date_id)")
    conds += [f"(s.{c} IS NULL OR s.{c} >= 0)" for c in t.columns if meta[c].nonneg]
    where = " AND ".join(conds) if conds else "true"
    lookup_selects = "".join(
        f", {_lookup_value(i, lk)} AS {lk.column}" for i, lk in enumerate(t.lookups)
    )
    insertable = (
        "insertable AS (\n"
        f"  SELECT s.*{lookup_selects}\n"
        f"  FROM deduped s{joins}\n"
        f"  WHERE {where}\n"
        ")"
    )
    return f"WITH {cte},\n{insertable}"


def upsert_sql(conn: Connection, name: str) -> str:
    t = TARGETS[name]
    meta = _table_meta(conn, name)
    with_clause = _with_insertable(conn, name)
    insert_cols = [*t.columns, *(lk.column for lk in t.lookups), "src_system", "load_id",
                   "updated_at"]
    # Fix r1, I3: kalit yo'q (bo'lmagan) bo'lsa — jadval DEFAULT'i (masalan 0), NULL emas.
    exprs = [
        f"coalesce(i.{c}, {meta[c].default_sql})" if meta[c].default_sql is not None
        else f"i.{c}"
        for c in t.columns
    ]
    exprs += [f"i.{lk.column}" for lk in t.lookups]
    exprs += [":source", ":load_id", "now()"]
    updatable = _updatable(t)
    set_list = [f"{c} = EXCLUDED.{c}" for c in updatable]
    set_list += ["load_id = EXCLUDED.load_id", "updated_at = now()"]
    # Shifrmatn har safar boshqacha (tasodifiy nonce) — o'zgarishni blind index bo'yicha aniqlaymiz.
    encrypted = {s.enc_column for s in t.sensitive}
    compared = [c for c in updatable if c not in encrypted]
    old = ", ".join(f"t.{c}" for c in compared)
    new = ", ".join(f"EXCLUDED.{c}" for c in compared)
    return (
        f"{with_clause}\n"
        f"INSERT INTO dwh.{name} AS t ({', '.join(insert_cols)})\n"
        f"SELECT {', '.join(exprs)}\n"
        "FROM insertable i\n"
        f"ON CONFLICT ({', '.join(t.conflict)}) DO UPDATE SET {', '.join(set_list)}\n"
        f"WHERE ({old}) IS DISTINCT FROM ({new})"
    )


def _moved_sql(conn: Connection, name: str) -> str:
    # Hujjat sanasi o'zgargan bo'lsa, eski partitsiyadagi nusxani o'chiramiz — faqat
    # `insertable` (tasdiqlangan, deduplikatsiya qilingan) qatorlar uchun (fix r1, M1/I2).
    with_clause = _with_insertable(conn, name)
    return (
        f"{with_clause}\n"
        f"DELETE FROM dwh.{name} t USING insertable i\n"
        "WHERE t.src_system = :source AND t.doc_type = i.doc_type AND t.src_id = i.src_id "
        "AND t.date_id <> i.date_id"
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


# ── Qator darajasidagi xatolar: har biri (select, count, limit bilan insert) uchligi
# (fix r1, M3) — MergeStats'dagi son ERROR_LIMIT bilan cheklanmagan haqiqiy sondan olinadi,
# `core.etl_error`ga yozish esa jadvalning cheksiz o'sishidan himoyalanadi.

def _type_error_select(conn: Connection, name: str) -> str:
    t = TARGETS[name]
    meta = _table_meta(conn, name)
    cases = [
        f"CASE WHEN s.payload->>'{c}' IS NOT NULL AND NOT pg_input_is_valid(s.payload->>'{c}', "
        f"'{meta[c].pg_type.replace(chr(39), chr(39) * 2)}') THEN '{c}' END"
        for c in t.columns
    ]
    return (
        "SELECT left(coalesce(s.payload->>'src_id', s.payload->>'code'), 128) AS src_id,\n"
        f"  COALESCE({', '.join(cases)}) AS field\n"
        "FROM stg.rows s WHERE s.load_id = :load_id AND s.target = :target"
    )


def _type_error_insert_sql(conn: Connection, name: str) -> str:
    select = _type_error_select(conn, name)
    return (
        "INSERT INTO core.etl_error (run_id, step, severity, target, src_id, code, message)\n"
        # `:target` shu so'rovda ikki xil kontekstda ishlatilgani sababli (INSERT nishon
        # ustuni vs ichki WHERE solishtiruv) psycopg AmbiguousParameter bilan yiqiladi —
        # birinchi CAST qolganini "ankarlaydi" (task-5-report.md'dagi round 0 tuzatishi).
        "SELECT :load_id, :step, 'error', CAST(:target AS varchar), x.src_id, 'invalid_type',\n"
        "  'Некорректное значение поля: ' || x.field\n"
        f"FROM ({select}) x WHERE x.field IS NOT NULL\nLIMIT {ERROR_LIMIT}"
    )


def _type_error_count_sql(conn: Connection, name: str) -> str:
    select = _type_error_select(conn, name)
    return f"SELECT count(*) FROM ({select}) x WHERE x.field IS NOT NULL"


def _negative_select(conn: Connection, name: str, col: str) -> str:
    cte = _staged_cte_sql(conn, name)
    return (
        f"WITH {cte}\n"
        "SELECT left(coalesce(deduped.payload->>'src_id', deduped.payload->>'code'), 128) "
        "AS src_id\n"
        f"FROM deduped WHERE deduped.{col} < 0"
    )


def _negative_insert_sql(conn: Connection, name: str, col: str) -> str:
    select = _negative_select(conn, name, col)
    return (
        "INSERT INTO core.etl_error (run_id, step, severity, target, src_id, code, message)\n"
        "SELECT :load_id, :step, 'error', CAST(:target AS varchar), x.src_id, 'negative_amount',\n"
        f"  'Отрицательное значение поля: {col}'\n"
        f"FROM ({select}) x\nLIMIT {ERROR_LIMIT}"
    )


def _negative_count_sql(conn: Connection, name: str, col: str) -> str:
    return f"SELECT count(*) FROM ({_negative_select(conn, name, col)}) x"


def _lookup_error_select(name: str, index: int) -> str:
    lk = TARGETS[name].lookups[index]
    key_expr = f"NULLIF(s.payload->>'{lk.key}', '')"  # fix r1, M2
    present = f"{key_expr} IS NOT NULL" if lk.nullable else "true"
    return (
        "SELECT left(coalesce(s.payload->>'src_id', s.payload->>'code'), 128) AS src_id,\n"
        f"  coalesce(s.payload->>'{lk.key}', '—') AS code_value\n"
        f"FROM stg.rows s LEFT JOIN dwh.{lk.dim} d ON d.code = {key_expr}\n"
        f"WHERE s.load_id = :load_id AND s.target = :target AND d.{lk.column} IS NULL "
        f"AND {present}"
    )


def _lookup_error_insert_sql(name: str, index: int) -> str:
    lk = TARGETS[name].lookups[index]
    select = _lookup_error_select(name, index)
    return (
        "INSERT INTO core.etl_error (run_id, step, severity, target, src_id, code, message)\n"
        f"SELECT :load_id, :step, '{lk.severity}', CAST(:target AS varchar), x.src_id,\n"
        f"  '{lk.error_code}', left('Не найден справочник {lk.dim}: ' || x.code_value, 500)\n"
        f"FROM ({select}) x\nLIMIT {ERROR_LIMIT}"
    )


def _lookup_error_count_sql(name: str, index: int) -> str:
    return f"SELECT count(*) FROM ({_lookup_error_select(name, index)}) x"


def _date_error_select(name: str) -> str:
    return (
        "SELECT left(s.payload->>'src_id', 128) AS src_id,\n"
        "  coalesce(s.payload->>'date_id', '—') AS date_value\n"
        "FROM stg.rows s WHERE s.load_id = :load_id AND s.target = :target AND "
        # Tur jihatidan noto'g'ri date_id allaqachon 'invalid_type' bilan qayd etiladi —
        # bu yerda faqat TUR TO'G'RI, lekin kalendarda yo'q sanalar hisoblanadi.
        "(s.payload->>'date_id' IS NOT NULL AND pg_input_is_valid(s.payload->>'date_id', "
        "'integer')) AND NOT EXISTS "
        "(SELECT 1 FROM dwh.dim_date dd WHERE dd.date_id::text = s.payload->>'date_id')"
    )


def _date_error_insert_sql(name: str) -> str:
    select = _date_error_select(name)
    return (
        "INSERT INTO core.etl_error (run_id, step, severity, target, src_id, code, message)\n"
        "SELECT :load_id, :step, 'error', CAST(:target AS varchar), x.src_id, 'missing_dim',\n"
        "  left('Дата вне справочника dim_date: ' || x.date_value, 500)\n"
        f"FROM ({select}) x\nLIMIT {ERROR_LIMIT}"
    )


def _date_error_count_sql(name: str) -> str:
    return f"SELECT count(*) FROM ({_date_error_select(name)}) x"


def staged_targets(conn: Connection, load_id: int) -> set[str]:
    return set(conn.execute(
        text("SELECT target FROM stg.batch WHERE load_id = :l"), {"l": load_id}).scalars())


def merge_target(conn: Connection, name: str, *, load_id: int, source: str, step: str,
                 as_of: date, window: Window | None = None, replace: bool = False) -> MergeStats:
    t = TARGETS[name]
    meta = _table_meta(conn, name)
    params = {"load_id": load_id, "source": source, "target": name, "step": step}
    errors = warnings = deleted = 0

    # I3: tur xatolari — birinchi, chunki qolgan barcha bosqichlar (dedup, lookup,
    # manfiylik) faqat tur-to'g'ri qatorlarga tegishli.
    errors += conn.execute(text(_type_error_count_sql(conn, name)), params).scalar_one()
    conn.execute(text(_type_error_insert_sql(conn, name)), params)

    for i, lk in enumerate(t.lookups):
        count = conn.execute(text(_lookup_error_count_sql(name, i)), params).scalar_one()
        conn.execute(text(_lookup_error_insert_sql(name, i)), params)
        if lk.fallback_sql:
            warnings += count
        else:
            errors += count

    if "date_id" in t.columns:
        errors += conn.execute(text(_date_error_count_sql(name)), params).scalar_one()
        conn.execute(text(_date_error_insert_sql(name)), params)

    for c in t.columns:
        if meta[c].nonneg:
            errors += conn.execute(text(_negative_count_sql(conn, name, c)), params).scalar_one()
            conn.execute(text(_negative_insert_sql(conn, name, c)), params)

    if t.partition is not None:
        deleted += conn.execute(text(_moved_sql(conn, name)), params).rowcount
    upserted = conn.execute(text(upsert_sql(conn, name)), params).rowcount
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
