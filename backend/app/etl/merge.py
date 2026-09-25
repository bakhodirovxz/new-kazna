"""stg → dwh (spec 5.2): idempotent upsert (faqat o'zgargan qatorlar), o'lcham kodlari → id,
statyasiz → «Прочие» (+ ogohlantirish), noma'lum filial/o'lcham → etl_error va qator
o'tkazib yuboriladi, oyna ichida to'liq almashtirish, SCD-2 versiyalari.

Barcha identifikatorlar app.dwh.targets reyestridan (whitelist).

Qator darajasidagi tekshiruv (fix r1 I3, fix r2 R2-1/R2-2/R2-3/R2-4) bitta partiyani BIR MARTA
`stg.rows`dan o'qib, `CREATE TEMP TABLE _merge_stage ... ON COMMIT DROP` ichiga materiallashtiradi
(R2-4 — har bir maqsad uchun bitta skan; oldingi versiyada har xato toifasi uchun alohida to'liq
qayta skan bor edi). Bosqichlar (barchasi bitta SQL ichida, CTE zanjiri):

1. `latest` — DUBLIKAT AVVAL (R2-3): bitta partiyada bir xil hujjat (yoki tabiiy kalit) bir necha
   marta kelsa, FAQAT eng oxirgisi (`seq` bo'yicha, XOM `payload`dan olingan) tekshiriladi — agar
   o'sha oxirgi qator yaroqsiz bo'lsa, HUJJAT BUTUNLAY o'tkazib yuboriladi (eski nusxaga QAYTIB
   TUSHILMAYDI — bu Round-1'dagi xato edi: dedup avval TUR-TO'G'RI qatorlar orasida bo'lgani
   uchun eski yaroqli versiya "g'olib" chiqishi mumkin edi).
2. `typed` — PG16 `pg_input_is_valid()` bilan har ustun turi tekshiriladi (katalogdan
   `format_type()` orqali olingan turlar — `_table_meta()`, jarayon davomida keshlanadi).
3. `populated` — FAQAT tur-to'g'ri qatorlar `jsonb_populate_record()`ga uzatiladi (xavfsiz).
4. `evaluated` — lookup'lar (LEFT JOIN), keyin BITTA ustuvorlik CASE zanjiri: yo'q qiymat
   (`missing_value`, DEFAULT'siz NOT NULL ustun), CHECK buzilishi (`check_violation` yoki
   `negative_amount` — katalogdan `pg_get_constraintdef()` orqali, umumiy, regex emas), lookup
   xatosi (`missing_branch`/`missing_item`/`missing_dim`), sana yo'qligi (`missing_dim`) — CASE
   birinchi mos kelgan shartda to'xtaydi (Postgres buni KAFOLATLAYDI, oddiy AND/OR emas — shu
   sababli bitta qator ikkita kod bilan ikki marta hisoblanmaydi, fix r2 Minor 6). Statya
   fallback'li lookup (masalan item_id) hech qachon qatorni bloklamaydi — alohida
   `warning`-darajali ustunlarda kuzatiladi.

Xato xabarlarida HECH QACHON xom qiymat yo'q (faqat ustun/cheklov nomi) — sezgir maydonlar esa
umuman staging'ga tushmaydi (`app.etl.staging.protect()`).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.dwh import partitions
from app.dwh.targets import DIM_TARGETS, FACT_TARGETS, TARGETS, Lookup, Target
from app.etl.types import Window

ERROR_LIMIT = 1000
STAGE_TABLE = "_merge_stage"


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
    not_null: bool


@dataclass(frozen=True, slots=True)
class CheckMeta:
    name: str  # cheklov nomi (masalan "fact_cashflow_amount_check") — xatoda shu ko'rsatiladi
    expr: str  # "CHECK " prefiksisiz ifoda, ustun nomlari UNQUALIFIED (populated'ga mos)
    code: str  # 'negative_amount' (oddiy `col >= 0` ko'rinishi) yoki umumiy 'check_violation'
    columns: frozenset[str]  # ifoda tegishli ustunlar — faqat shular staging'da bo'lsa ishlatiladi


@dataclass(frozen=True, slots=True)
class TableMeta:
    columns: dict[str, ColumnMeta]
    checks: tuple[CheckMeta, ...]


# Fix r2, "restart after migrations": katalog metadata JARAYON davomida (bir marta so'ralib)
# keshlanadi — sxema o'zgarsa (yangi migratsiya) worker/API jarayoni qayta ishga tushirilishi
# kerak, aks holda eski (keshlangan) ustun/cheklov ro'yxati ishlatilib qolaveradi.
_META_CACHE: dict[str, TableMeta] = {}


def _check_code(expr: str, columns: Sequence[str]) -> str:
    stripped = expr.strip()
    for col in columns:
        pattern = rf"^\(*\s*{re.escape(col)}\s*>=\s*\(?0\)?(?:::numeric)?\s*\)*$"
        if re.match(pattern, stripped):
            return "negative_amount"
    return "check_violation"


def _table_meta(conn: Connection, table: str) -> TableMeta:
    cached = _META_CACHE.get(table)
    if cached is not None:
        return cached
    cols = conn.execute(
        text(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod), "
            "pg_get_expr(d.adbin, d.adrelid), a.attnotnull "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
            "WHERE n.nspname = 'dwh' AND c.relname = :t AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"t": table},
    ).all()
    columns = {
        name: ColumnMeta(pg_type, default_sql, not_null)
        for name, pg_type, default_sql, not_null in cols
    }
    check_rows = conn.execute(
        text(
            "SELECT co.conname, pg_get_constraintdef(co.oid),\n"
            "  (SELECT array_agg(a.attname) FROM unnest(co.conkey) k(attnum)\n"
            "   JOIN pg_attribute a ON a.attrelid = co.conrelid AND a.attnum = k.attnum)\n"
            "FROM pg_constraint co\n"
            "WHERE co.conrelid = to_regclass('dwh.' || :t) AND co.contype = 'c'"
        ),
        {"t": table},
    ).all()
    col_names = tuple(columns)
    checks = tuple(
        CheckMeta(
            conname,
            defn.removeprefix("CHECK "),
            _check_code(defn.removeprefix("CHECK "), col_names),
            frozenset(cols_ref or ()),
        )
        for conname, defn, cols_ref in check_rows
    )
    meta = TableMeta(columns, checks)
    # Fix r2, Minor 5: bo'sh (jadval hali yo'q) natija keshlanmaydi.
    if columns:
        _META_CACHE[table] = meta
    return meta


def _dedupe_keys(t: Target) -> list[str]:
    # Fix r1, I2: partitsiyalangan faktlarda bitta partiyada bir xil hujjat turli sanada
    # ikki marta kelsa, `date_id`ni HISOBGA OLMAY (doc_type, src_id) bo'yicha dublikat olib
    # tashlanadi — oxirgisi (`seq` bo'yicha) g'olib. Boshqa maqsadlarda (jumladan fx_rate,
    # unda date_id tabiiy kalitning bir qismi) tabiiy kalit o'zgarishsiz qoladi.
    if t.partition is not None:
        return ["doc_type", "src_id"]
    return [c for c in t.conflict if c != "src_system"]


def _lookup_value(i: int, lk: Lookup) -> str:
    if lk.fallback_sql is None:
        return f"l{i}.{lk.column}"
    return (f"coalesce(l{i}.{lk.column}, (SELECT fb.{lk.column} FROM dwh.{lk.dim} fb "
            f"WHERE fb.code = {lk.fallback_sql}))")


def _updatable(t: Target) -> list[str]:
    data = [*t.columns, *(lk.column for lk in t.lookups)]
    cols = [c for c in data if c not in t.conflict]
    if "src_system" not in t.conflict:
        cols.append("src_system")
    return cols


def _case(branches: list[tuple[str, str, str]], field: int) -> str:
    """`branches` — (shart, kod-ifoda, tafsilot-ifoda) uchliklar ro'yxati, ustuvorlik tartibida.
    `field` 1 — kod, 2 — tafsilot. CASE birinchi TO'G'RI shartda to'xtaydi (Postgres buni
    kafolatlaydi — oddiy AND/OR farqli o'laroq), shu bilan bitta qator faqat BITTA sabab bilan
    hisoblanadi (fix r2, Minor 6)."""
    if not branches:
        return "NULL"
    whens = "\n    ".join(f"WHEN {b[0]} THEN {b[field]}" for b in branches)
    return f"(CASE\n    {whens}\n  END)"


def _stage_create_sql(conn: Connection, name: str) -> str:
    t = TARGETS[name]
    tmeta = _table_meta(conn, name)
    dedupe_keys = _dedupe_keys(t)
    dedupe_exprs = ", ".join(f"payload->>'{c}'" for c in dedupe_keys)

    type_cases = [
        f"CASE WHEN payload->>'{c}' IS NOT NULL AND NOT pg_input_is_valid(payload->>'{c}', "
        f"'{tmeta.columns[c].pg_type.replace(chr(39), chr(39) * 2)}') THEN '{c}' END"
        for c in t.columns
    ]
    populated_cols = ", ".join(f"r.{c}" for c in t.columns)

    # R2-1: DEFAULT'siz NOT NULL ustun yo'q/NULL bo'lsa — 'missing_value'.
    required = [
        c for c in t.columns
        if tmeta.columns[c].not_null and tmeta.columns[c].default_sql is None
    ]
    # R2-1: umumiy CHECK tekshiruvi — faqat staging ustunlariga tegishli cheklovlar (boshqa
    # ustunlarga, masalan surrogat PK'ga tegishli cheklov `populated`da mavjud emas).
    usable_checks = [c for c in tmeta.checks if c.columns and c.columns <= set(t.columns)]

    # Fix r1, targets.py's `_ITEM_BY_DIRECTION` fallback_sql qat'iy "s.payload->>'direction'"
    # deb yozilgan (round-1 konvensiyasi) — shu sababli qator manbasi shu yerda ham "s" deb
    # nomlanadi (jsonb qatoridan chiqarilgan `populated`/`evaluated` qatori), "raw" CTE'dagi
    # `stg.rows s` esa BUTUNLAY BOSHQA (ichki) doira — ikkalasi to'qnashmaydi.
    joins = "".join(
        f"\n  LEFT JOIN dwh.{lk.dim} l{i} ON l{i}.code = NULLIF(s.payload->>'{lk.key}', '')"
        for i, lk in enumerate(t.lookups)
    )
    lookup_cols = [f"{_lookup_value(i, lk)} AS {lk.column}" for i, lk in enumerate(t.lookups)]
    lookup_cols_sel = "".join(f", {c}" for c in lookup_cols)
    lookup_names = [lk.column for lk in t.lookups]

    # `early_branches` — hali JOIN qilinmagan `populated` doirasida baholanadi (`checked` CTE):
    # bu ustunlar (missing_value/CHECK) faqat `t.columns`ga tegishli, LEKIN ba'zi lookup o'lchov
    # jadvallari xuddi shu nomdagi ustunga ega bo'lishi mumkin (masalan dim_contract.amount) —
    # agar shu tekshiruvlar JOIN'lardan KEYIN (evaluated'da) baholansa, unqualified ustun nomi
    # (masalan "amount") AmbiguousColumn bilan yiqiladi. Shu sababli ular OLDINROQ, hali hech
    # qanday lookup jadvali qo'shilmagan bosqichda hisoblanadi.
    early_branches: list[tuple[str, str, str]] = []
    for c in required:
        early_branches.append((f"s.{c} IS NULL", "'missing_value'", f"'{c}'"))
    for chk in usable_checks:
        early_branches.append(
            (f"NOT coalesce(({chk.expr}), true)", f"'{chk.code}'", f"'{chk.name}'"))

    # `late_branches` — lookup/sana tekshiruvi, faqat JOIN qilingandan keyin (evaluated'da).
    late_branches: list[tuple[str, str, str]] = []
    for i, lk in enumerate(t.lookups):
        if lk.fallback_sql is not None:
            continue  # statyasiz -> «Прочие»: bloklamaydi, faqat ogohlantirish (pastda)
        key_expr = f"NULLIF(s.payload->>'{lk.key}', '')"
        cond = (f"({key_expr} IS NOT NULL AND l{i}.{lk.column} IS NULL)" if lk.nullable
                else f"l{i}.{lk.column} IS NULL")
        detail = f"left('Не найден справочник {lk.dim}: ' || coalesce({key_expr}, '—'), 500)"
        late_branches.append((cond, f"'{lk.error_code}'", detail))
    if "date_id" in t.columns:
        late_branches.append((
            "NOT EXISTS (SELECT 1 FROM dwh.dim_date x WHERE x.date_id = s.date_id)",
            "'missing_dim'",
            "left('Дата вне справочника dim_date: ' || coalesce(s.date_id::text, '—'), 500)",
        ))

    warn_branches = [
        (f"l{i}.{lk.column} IS NULL", f"'{lk.error_code}'",
         f"left('Не найден справочник {lk.dim}: ' || "
         f"coalesce(NULLIF(s.payload->>'{lk.key}', ''), '—'), 500)")
        for i, lk in enumerate(t.lookups) if lk.fallback_sql is not None
    ]

    early_code_case = _case(early_branches, 1)
    early_detail_case = _case(early_branches, 2)
    # Ustuvorlik: agar `checked` bosqichida allaqachon sabab topilgan bo'lsa (early_code IS NOT
    # NULL) — o'sha birinchi (Postgres CASE kafolatlaydi), aks holda lookup/sana navbati
    # (fix r1, M1/Minor 6: bitta qator faqat bitta sabab bilan hisoblanadi).
    code_case = _case([("s.early_code IS NOT NULL", "s.early_code", ""), *late_branches], 1)
    detail_case = _case([("s.early_code IS NOT NULL", "", "s.early_detail"), *late_branches], 2)
    warn_code_case = _case(warn_branches, 1)
    warn_detail_case = _case(warn_branches, 2)

    cols_list = ", ".join(t.columns)
    lookup_names_list = (", " + ", ".join(lookup_names)) if lookup_names else ""
    null_cols = ", ".join("NULL" for _ in t.columns)
    null_lookup_names = (", " + ", ".join("NULL" for _ in lookup_names)) if lookup_names else ""

    valid_select = (
        "SELECT s.seq, (error_code IS NULL) AS ok, error_code,\n"
        "  (CASE WHEN error_code IS NOT NULL THEN 'error' END) AS error_severity, error_detail,\n"
        "  warn_code, warn_detail,\n"
        "  left(coalesce(s.payload->>'src_id', s.payload->>'code'), 128) AS stage_src_id,\n"
        f"  {cols_list}{lookup_names_list}\n"
        "FROM evaluated s"
    )
    invalid_select = (
        "SELECT t.seq, false AS ok, 'invalid_type' AS error_code, 'error' AS error_severity,\n"
        "  ('Некорректное значение поля: ' || t.bad_field) AS error_detail,\n"
        "  NULL AS warn_code, NULL AS warn_detail,\n"
        "  left(coalesce(t.payload->>'src_id', t.payload->>'code'), 128) AS stage_src_id,\n"
        f"  {null_cols}{null_lookup_names}\n"
        "FROM typed t WHERE t.bad_field IS NOT NULL"
    )

    return (
        f"CREATE TEMP TABLE {STAGE_TABLE} ON COMMIT DROP AS\n"
        "WITH raw AS (\n"
        "  SELECT s.seq, s.payload FROM stg.rows s\n"
        "  WHERE s.load_id = :load_id AND s.target = :target\n"
        "),\n"
        # Fix r2, R2-3: dublikat TEKSHIRUVDAN OLDIN — xom `payload` matni bo'yicha, eng oxirgi
        # qator (istalgan holatda) tanlanadi; faqat o'sha bitta qator keyin tekshiriladi.
        "latest AS (\n"
        f"  SELECT DISTINCT ON ({dedupe_exprs}) seq, payload\n"
        "  FROM raw\n"
        f"  ORDER BY {dedupe_exprs}, seq DESC\n"
        "),\n"
        "typed AS (\n"
        f"  SELECT seq, payload, COALESCE({', '.join(type_cases)}) AS bad_field\n"
        "  FROM latest\n"
        "),\n"
        "populated AS (\n"
        f"  SELECT s.seq, s.payload, {populated_cols}\n"
        "  FROM (SELECT seq, payload FROM typed WHERE bad_field IS NULL) s\n"
        f"  CROSS JOIN LATERAL jsonb_populate_record(NULL::dwh.{name}, s.payload) r\n"
        "),\n"
        # JOIN'lardan OLDIN: missing_value/CHECK — unqualified ustun nomlari shu yerda
        # ANIQ (JOIN qilingan lookup jadvalida bir xil nomli ustun bo'lishi mumkin).
        "checked AS (\n"
        f"  SELECT s.*, {early_code_case} AS early_code, {early_detail_case} AS early_detail\n"
        "  FROM populated s\n"
        "),\n"
        "evaluated AS (\n"
        f"  SELECT s.*{lookup_cols_sel},\n"
        f"    {code_case} AS error_code,\n"
        f"    {detail_case} AS error_detail,\n"
        f"    {warn_code_case} AS warn_code,\n"
        f"    {warn_detail_case} AS warn_detail\n"
        f"  FROM checked s{joins}\n"
        ")\n"
        f"{valid_select}\n"
        "UNION ALL\n"
        f"{invalid_select}"
    )


def upsert_sql(conn: Connection, name: str) -> str:
    t = TARGETS[name]
    tmeta = _table_meta(conn, name)
    insert_cols = [*t.columns, *(lk.column for lk in t.lookups), "src_system", "load_id",
                   "updated_at"]
    exprs = [
        f"coalesce(s.{c}, {tmeta.columns[c].default_sql})"
        if tmeta.columns[c].default_sql is not None else f"s.{c}"
        for c in t.columns
    ]
    exprs += [f"s.{lk.column}" for lk in t.lookups]
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
        f"INSERT INTO dwh.{name} AS t ({', '.join(insert_cols)})\n"
        f"SELECT {', '.join(exprs)}\n"
        f"FROM {STAGE_TABLE} s WHERE s.ok\n"
        f"ON CONFLICT ({', '.join(t.conflict)}) DO UPDATE SET {', '.join(set_list)}\n"
        f"WHERE ({old}) IS DISTINCT FROM ({new})"
    )


@cache
def _moved_sql(name: str) -> str:
    # Hujjat sanasi o'zgargan bo'lsa, eski partitsiyadagi nusxani o'chiramiz — faqat
    # `_merge_stage`dagi TASDIQLANGAN (`ok`) qatorlar uchun (fix r1, M1/I2).
    return (
        f"DELETE FROM dwh.{name} t USING {STAGE_TABLE} s\n"
        "WHERE s.ok AND t.src_system = :source AND t.doc_type = s.doc_type "
        "AND t.src_id = s.src_id AND t.date_id <> s.date_id"
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


_ERROR_COUNT_SQL = f"SELECT count(*) FROM {STAGE_TABLE} WHERE NOT ok"
_ERROR_INSERT_SQL = (
    "INSERT INTO core.etl_error (run_id, step, severity, target, src_id, code, message)\n"
    "SELECT :load_id, :step, error_severity, CAST(:target AS varchar), stage_src_id, error_code, "
    f"error_detail\nFROM {STAGE_TABLE} WHERE NOT ok\nLIMIT {ERROR_LIMIT}"
)
_WARNING_COUNT_SQL = f"SELECT count(*) FROM {STAGE_TABLE} WHERE warn_code IS NOT NULL"
_WARNING_INSERT_SQL = (
    "INSERT INTO core.etl_error (run_id, step, severity, target, src_id, code, message)\n"
    "SELECT :load_id, :step, 'warning', CAST(:target AS varchar), stage_src_id, warn_code, "
    f"warn_detail\nFROM {STAGE_TABLE} WHERE warn_code IS NOT NULL\nLIMIT {ERROR_LIMIT}"
)


def merge_target(conn: Connection, name: str, *, load_id: int, source: str, step: str,
                 as_of: date, window: Window | None = None, replace: bool = False) -> MergeStats:
    t = TARGETS[name]
    params = {"load_id": load_id, "source": source, "target": name, "step": step}

    # Fix r2, R2-4: bitta partiya uchun bitta materiallashtirish — pastdagi barcha hisob va
    # yozuvlar shu jadvaldan, stg.rows'ni qayta skanlamay olinadi.
    conn.execute(text(f"DROP TABLE IF EXISTS pg_temp.{STAGE_TABLE}"))
    conn.execute(text(_stage_create_sql(conn, name)), params)

    errors = conn.execute(text(_ERROR_COUNT_SQL)).scalar_one()
    conn.execute(text(_ERROR_INSERT_SQL), params)
    warnings = conn.execute(text(_WARNING_COUNT_SQL)).scalar_one()
    conn.execute(text(_WARNING_INSERT_SQL), params)

    deleted = 0
    if t.partition is not None:
        deleted += conn.execute(text(_moved_sql(name)), params).rowcount
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
