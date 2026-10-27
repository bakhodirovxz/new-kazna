"""Fix r1 (I1): `dwh`/`mart` sxemalaridagi RLS tuzilishi va `ugk_app`ning shifrlangan
vitrina rekvizitlariga huquqi yo'qligi.

Structural introspeksiya (`test_every_branch_id_table_has_rls_enabled_and_forced`) aniq
jadval nomlarini sanab o'tirmaydi — `branch_id` ustuni bor HAR BIR jadvalni topadi va
tekshiradi, shuning uchun keyingi vazifalarda yangi `dwh`/`mart` jadvali qo'shilganda bu
test uni avtomatik qamrab oladi (RLS yoqilishini "unutib qo'yish" jimgina o'tib ketmaydi).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.core.db import get_engine, new_session
from app.etl.db import etl_transaction

_SCHEMAS = ("dwh", "mart")


def _tables_with_branch_id() -> list[tuple[str, str]]:
    """`branch_id` ustunli har bir MANTIQIY jadval — `NOT relispartition` RANGE-partitsiya
    qilingan jadvallarning har bir oylik bo'limini alohida "jadval" sifatida
    ko'paytirib yubormasligi uchun (`test_reencrypt_registry.py`dagi bilan bir xil sabab)."""
    with get_engine("migrator").connect() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT n.nspname, c.relname FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = ANY(:schemas) AND c.relkind IN ('r', 'p') "
                "AND NOT c.relispartition AND a.attname = 'branch_id' AND a.attnum > 0 "
                "AND NOT a.attisdropped ORDER BY 1, 2"
            ),
            {"schemas": list(_SCHEMAS)},
        ).all()
    return [(schema, table) for schema, table in rows]


def test_every_branch_id_table_has_rls_enabled_and_forced() -> None:
    tables = _tables_with_branch_id()
    # Isbot: introspeksiya haqiqatan ham biror narsa topayotganini tasdiqlaydi (aks holda
    # bo'sh ro'yxat bilan pastdagi tsikl "ko'r" bo'lib o'tib ketardi).
    assert {"dim_branch", "dim_branch_version", "dim_contract", "dim_loan"} <= {
        t for _, t in tables
    }
    with get_engine("migrator").connect() as conn:
        for schema, table in tables:
            row = conn.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :s AND c.relname = :t"
                ),
                {"s": schema, "t": table},
            ).one()
            assert row.relrowsecurity, f"{schema}.{table}: RLS yoqilmagan"
            assert row.relforcerowsecurity, f"{schema}.{table}: FORCE RLS yo'q"


def _fact_partitions() -> list[tuple[str, str]]:
    """`dwh`/`mart`dagi HAR BIR partitsiya (RANGE partitsiyalangan fakt jadvallarining
    oylik/yillik bo'limlari) — yuqoridagi `_tables_with_branch_id()` ATAYLAB bularni
    chiqarib tashlaydi (`NOT c.relispartition`), chunki ular alohida "mantiqiy jadval"
    emas. Bu yordamchi esa aynan o'sha chetlab o'tilgan partitsiyalarni topadi — mudofaa
    chuqurligi (fix r1, I2): partitsiyalar RLS'ni ota-jadvaldan faqat so'rov ota orqali
    yo'naltirilganda meros oladi, to'g'ridan-to'g'ri (partitsiya nomi bilan) so'ralganda
    ham himoyalangan bo'lishi kerak."""
    with get_engine("migrator").connect() as conn:
        rows = conn.execute(
            text(
                "SELECT n.nspname, c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                # relkind = 'r': faqat oddiy jadval partitsiyalari — relispartition
                # partitsiyalangan INDEKSlarning bo'lim-indekslarida ham true bo'ladi
                # (relkind = 'i'), ular RLS/GRANT bilan aloqasi yo'q.
                "WHERE n.nspname = ANY(:schemas) AND c.relispartition AND c.relkind = 'r' "
                "ORDER BY 1, 2"
            ),
            {"schemas": list(_SCHEMAS)},
        ).all()
    return [(schema, table) for schema, table in rows]


def test_every_fact_partition_has_rls_enabled_and_forced() -> None:
    """Fix r1 (I2, b): `dwh.ensure_partitions` har bir yangi partitsiyada ENABLE/FORCE RLS
    o'rnatishi kerak — migratsiyaning o'zi `upgrade()` oxirida joriy oy/yil uchun dastlabki
    partitsiyalarni shu funksiya orqali yaratadi, shuning uchun bu test alohida fixture'siz
    ham kamida bir nechta partitsiyani topadi."""
    partitions_ = _fact_partitions()
    assert partitions_, "hech qanday fakt partitsiyasi topilmadi — migratsiya ishlamadimi?"
    with get_engine("migrator").connect() as conn:
        for schema, table in partitions_:
            row = conn.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :s AND c.relname = :t"
                ),
                {"s": schema, "t": table},
            ).one()
            assert row.relrowsecurity, f"{schema}.{table}: RLS yoqilmagan (partitsiya)"
            assert row.relforcerowsecurity, f"{schema}.{table}: FORCE RLS yo'q (partitsiya)"


def test_no_role_has_direct_privileges_on_fact_partitions() -> None:
    """Fix r1 (I2, a): `ugk_app`/`ugk_etl`ning HECH bir fakt partitsiyasida to'g'ridan-to'g'ri
    huquqi yo'q — GRANT faqat ota (partitsiyalangan) jadvalga berilgan (0006), partitsiyalar
    faqat ota orqali so'ralganda ko'rinadi. Yuqoridagi RLS testi bilan birga: hatto kimdir
    partitsiya nomini to'g'ridan-to'g'ri bilsa ham, u avval huquq yo'qligiga (bu test), keyin
    RLS'ga (oldingi test) duch keladi."""
    partitions_ = _fact_partitions()
    assert partitions_
    with get_engine("migrator").connect() as conn:
        for schema, table in partitions_:
            for role in ("ugk_app", "ugk_etl"):
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    ok = conn.execute(
                        text("SELECT has_table_privilege(:r, :t, :p)"),
                        {"r": role, "t": f"{schema}.{table}", "p": priv},
                    ).scalar_one()
                    assert not ok, f"{role} {priv} huquqiga ega: {schema}.{table}"


def test_ugk_app_denied_select_on_dim_counterparty() -> None:
    """I1: `ugk_app` (internetga qaragan, keyring ushlab turadigan ulanish) `dwh.
    dim_counterparty`ga (hatto shifrlanmagan `name` ustuniga ham) hech qanday huquqqa ega
    emas — faqat operator CLI (migrator ulanishi) shifrlangan `inn_enc`ni qayta shifrlaydi."""
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("SELECT name FROM dwh.dim_counterparty"))


def test_ugk_app_denied_select_on_dim_bank() -> None:
    # 0022: tanlov ro'yxati uchun faqat sezgir bo'lmagan ustunlar; shifrlangan hisob -- yo'q.
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("SELECT account_enc FROM dwh.dim_bank"))
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("SELECT account_bidx FROM dwh.dim_bank"))
    with new_session() as s:
        s.execute(text("SELECT code, bank_name, currency, account_last4 FROM dwh.dim_bank"))


def test_ugk_app_denied_select_on_dim_contract() -> None:
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("SELECT contract_id FROM dwh.dim_contract"))


def test_ugk_app_denied_select_on_fx_rate() -> None:
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("SELECT rate FROM dwh.fx_rate"))


def _set_scope(conn: Connection, branch_ids: str) -> None:
    conn.execute(
        text(
            "SELECT set_config('app.scope_all', 'off', true), "
            "set_config('app.branch_ids', :ids, true)"
        ),
        {"ids": branch_ids},
    )


def test_dim_contract_rls_filters_by_branch() -> None:
    """`ugk_etl`ga `dwh.dim_contract`da to'liq DML huquqi berilgan (ETL yozadi uchun), lekin
    u jadval EGASI emas — `FORCE ROW LEVEL SECURITY` uni ham cheklaydi. Shu sabab bu yerda
    `ugk_app` emas, `ugk_etl` ulanishi RLS sozlamalari qo'lda (scope_all=off) o'rnatilib
    ishlatiladi — `etl_transaction()` (scope_all='on') ataylab ishlatilmaydi."""
    code = f"CT-R{uuid.uuid4().hex[:8]}"
    cp_code = f"CP-R{uuid.uuid4().hex[:8]}"
    with etl_transaction() as conn:
        cp_id = conn.execute(
            text(
                "INSERT INTO dwh.dim_counterparty (code, name, kind, src_system) "
                "VALUES (:c, 'X', 'supplier', 'test') RETURNING cp_id"
            ),
            {"c": cp_code},
        ).scalar_one()
        contract_id = conn.execute(
            text(
                "INSERT INTO dwh.dim_contract (code, number, contract_date, cp_id, branch_id, "
                "amount, kind, src_system) VALUES (:code, 'N-1', current_date, :cp, 5, 100, "
                "'payable', 'test') RETURNING contract_id"
            ),
            {"code": code, "cp": cp_id},
        ).scalar_one()
    try:
        with get_engine("etl").begin() as conn:
            _set_scope(conn, "{2}")
            assert (
                conn.execute(
                    text("SELECT contract_id FROM dwh.dim_contract WHERE code = :c"), {"c": code}
                ).all()
                == []
            )
        with get_engine("etl").begin() as conn:
            _set_scope(conn, "{5}")
            assert list(
                conn.execute(
                    text("SELECT contract_id FROM dwh.dim_contract WHERE code = :c"), {"c": code}
                ).scalars()
            ) == [contract_id]
    finally:
        with etl_transaction() as conn:
            conn.execute(
                text("DELETE FROM dwh.dim_contract WHERE contract_id = :i"), {"i": contract_id}
            )
            conn.execute(text("DELETE FROM dwh.dim_counterparty WHERE cp_id = :i"), {"i": cp_id})


def test_dim_loan_rls_filters_by_branch() -> None:
    code = f"LN-R{uuid.uuid4().hex[:8]}"
    with etl_transaction() as conn:
        loan_id = conn.execute(
            text(
                "INSERT INTO dwh.dim_loan (code, creditor, project, currency, rate, maturity, "
                "amount_uzs, branch_id, src_system) VALUES (:c, 'IFI', 'Loyiha', 'USD', 0.05, "
                "date '2035-01-01', 1000, 6, 'test') RETURNING loan_id"
            ),
            {"c": code},
        ).scalar_one()
    try:
        with get_engine("etl").begin() as conn:
            _set_scope(conn, "{2}")
            assert (
                conn.execute(
                    text("SELECT loan_id FROM dwh.dim_loan WHERE code = :c"), {"c": code}
                ).all()
                == []
            )
        with get_engine("etl").begin() as conn:
            _set_scope(conn, "{6}")
            assert list(
                conn.execute(
                    text("SELECT loan_id FROM dwh.dim_loan WHERE code = :c"), {"c": code}
                ).scalars()
            ) == [loan_id]
    finally:
        with etl_transaction() as conn:
            conn.execute(text("DELETE FROM dwh.dim_loan WHERE loan_id = :i"), {"i": loan_id})


def test_branch_version_overlap_with_current_rejected() -> None:
    """Har bir filial uchun joriy versiya `[2000-01-01, cheksiz)` oralig'ini egallaydi —
    istalgan yangi versiya oralig'i u bilan kesishadi, `EXCLUDE USING gist` buni rad etadi
    (fix r1: SCD-2 davr-qoplanish tekshiruvi).

    `begin_nested()` (SAVEPOINT) — kutilgan xatodan keyin ham tashqi `etl_transaction()`
    tranzaksiyasi "aborted" holatga tushib qolmasligi va normal COMMIT bo'la olishi uchun
    (aks holda tashqi `with` chiqishda o'zi ham kutilmagan xato bilan yiqilardi)."""
    with etl_transaction() as conn, pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(
            text(
                "INSERT INTO dwh.dim_branch_version (branch_id, capacity_mw, valid_from, "
                "valid_to, is_current) VALUES (2, 700, date '2020-01-01', "
                "date '2021-01-01', false)"
            )
        )


def test_branch_version_boundary_dates() -> None:
    """Fix r2: `valid_to` INKLYUZIV deb hisoblanadi (reja: yopish `valid_to = as_of - 1`
    belgilaydi, join'lar `d.date <= v.valid_to` ishlatadi) — `EXCLUDE` endi
    `daterange(..., '[]')` bilan ikkala chegarani ham kiritadi:

    1. yangi versiya `valid_from`i oldingisining `valid_to`iga TENG bo'lsa — kesishadi,
       rad etiladi (ikkalasi ham o'sha kunni "egallaydi");
    2. `valid_from = oldingi valid_to + 1` bo'lsa — kesishmaydi, qabul qilinadi;
    3. bir kunlik versiya (`valid_from = valid_to`) — qonuniy, qabul qilinadi (`CHECK`
       endi `>=`, qattiqroq `>` emas).

    `branch_id=8` vaqtincha yopiladi (boshqa testlar undan foydalanmaydi) va test oxirida
    aniq asl holatiga (`valid_from='2000-01-01'`, `is_current=true`, `valid_to=NULL`)
    qaytariladi — `test_dwh_dims.py::test_sixteen_branches_seeded` filiallar 1..16 uchun
    aynan bitta joriy versiya borligini hisoblaydi."""
    branch_id = 8
    with etl_transaction() as conn:
        conn.execute(
            text(
                "UPDATE dwh.dim_branch_version SET is_current = false, "
                "valid_to = date '2024-06-30' WHERE branch_id = :b AND is_current"
            ),
            {"b": branch_id},
        )
    try:
        with etl_transaction() as conn, pytest.raises(IntegrityError), conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO dwh.dim_branch_version (branch_id, valid_from, valid_to, "
                    "is_current) VALUES (:b, date '2024-06-30', date '2024-07-15', false)"
                ),
                {"b": branch_id},
            )
        with etl_transaction() as conn:
            conn.execute(
                text(
                    "INSERT INTO dwh.dim_branch_version (branch_id, valid_from, valid_to, "
                    "is_current) VALUES (:b, date '2024-07-01', date '2024-07-31', false)"
                ),
                {"b": branch_id},
            )
        with etl_transaction() as conn:
            conn.execute(
                text(
                    "INSERT INTO dwh.dim_branch_version (branch_id, valid_from, valid_to, "
                    "is_current) VALUES (:b, date '2024-08-15', date '2024-08-15', false)"
                ),
                {"b": branch_id},
            )
        with etl_transaction() as conn:
            rows = conn.execute(
                text(
                    "SELECT valid_from, valid_to FROM dwh.dim_branch_version "
                    "WHERE branch_id = :b AND valid_from <> date '2000-01-01' ORDER BY valid_from"
                ),
                {"b": branch_id},
            ).all()
        assert [(r.valid_from.isoformat(), r.valid_to.isoformat()) for r in rows] == [
            ("2024-07-01", "2024-07-31"),
            ("2024-08-15", "2024-08-15"),
        ]
    finally:
        with etl_transaction() as conn:
            conn.execute(
                text(
                    "DELETE FROM dwh.dim_branch_version WHERE branch_id = :b "
                    "AND valid_from <> date '2000-01-01'"
                ),
                {"b": branch_id},
            )
            conn.execute(
                text(
                    "UPDATE dwh.dim_branch_version SET is_current = true, valid_to = NULL "
                    "WHERE branch_id = :b AND valid_from = date '2000-01-01'"
                ),
                {"b": branch_id},
            )


def test_loan_version_overlap_rejected() -> None:
    code = f"LN-O{uuid.uuid4().hex[:8]}"
    with etl_transaction() as conn:
        loan_id = conn.execute(
            text(
                "INSERT INTO dwh.dim_loan (code, creditor, project, currency, rate, maturity, "
                "amount_uzs, branch_id, src_system) VALUES (:c, 'IFI', 'Loyiha', 'USD', 0.05, "
                "date '2035-01-01', 1000, 6, 'test') RETURNING loan_id"
            ),
            {"c": code},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO dwh.dim_loan_version (loan_id, rate, valid_from, valid_to, "
                "is_current) VALUES (:l, 0.05, date '2020-01-01', date '2022-01-01', false)"
            ),
            {"l": loan_id},
        )
        with pytest.raises(IntegrityError), conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO dwh.dim_loan_version (loan_id, rate, valid_from, "
                    "valid_to, is_current) VALUES (:l, 0.06, date '2021-01-01', "
                    "date '2023-01-01', false)"
                ),
                {"l": loan_id},
            )
        conn.execute(text("DELETE FROM dwh.dim_loan_version WHERE loan_id = :i"), {"i": loan_id})
        conn.execute(text("DELETE FROM dwh.dim_loan WHERE loan_id = :i"), {"i": loan_id})


def test_loan_version_boundary_dates() -> None:
    """Fix r3: `test_branch_version_boundary_dates`ning `dim_loan_version` uchun analogi —
    fix r2'da inklyuziv `valid_to`ga o'zgargan EXCLUDE/CHECK `dim_loan_version`da ham xuddi
    shunday ishlashi kerak:

    1. yangi versiya `valid_from`i oldingisining `valid_to`iga TENG bo'lsa — kesishadi,
       rad etiladi;
    2. `valid_from = oldingi valid_to + 1` bo'lsa — kesishmaydi, qabul qilinadi;
    3. bir kunlik versiya (`valid_from = valid_to`) — qonuniy, qabul qilinadi.

    O'zining alohida test kreditidan (`dim_loan`) foydalanadi — boshqa testlarga
    ta'sir qilmasligi uchun oxirida hammasi (versiyalar + kredit) o'chiriladi."""
    code = f"LN-B{uuid.uuid4().hex[:8]}"
    with etl_transaction() as conn:
        loan_id = conn.execute(
            text(
                "INSERT INTO dwh.dim_loan (code, creditor, project, currency, rate, maturity, "
                "amount_uzs, branch_id, src_system) VALUES (:c, 'IFI', 'Loyiha', 'USD', 0.05, "
                "date '2035-01-01', 1000, 7, 'test') RETURNING loan_id"
            ),
            {"c": code},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO dwh.dim_loan_version (loan_id, rate, valid_from, valid_to, "
                "is_current) VALUES (:l, 0.05, date '2020-01-01', date '2024-06-30', false)"
            ),
            {"l": loan_id},
        )
    try:
        with etl_transaction() as conn, pytest.raises(IntegrityError), conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO dwh.dim_loan_version (loan_id, rate, valid_from, valid_to, "
                    "is_current) VALUES (:l, 0.06, date '2024-06-30', date '2024-07-15', "
                    "false)"
                ),
                {"l": loan_id},
            )
        with etl_transaction() as conn:
            conn.execute(
                text(
                    "INSERT INTO dwh.dim_loan_version (loan_id, rate, valid_from, valid_to, "
                    "is_current) VALUES (:l, 0.06, date '2024-07-01', date '2024-07-31', "
                    "false)"
                ),
                {"l": loan_id},
            )
        with etl_transaction() as conn:
            conn.execute(
                text(
                    "INSERT INTO dwh.dim_loan_version (loan_id, rate, valid_from, valid_to, "
                    "is_current) VALUES (:l, 0.07, date '2024-08-15', date '2024-08-15', "
                    "false)"
                ),
                {"l": loan_id},
            )
        with etl_transaction() as conn:
            rows = conn.execute(
                text(
                    "SELECT valid_from, valid_to FROM dwh.dim_loan_version "
                    "WHERE loan_id = :l AND valid_from <> date '2020-01-01' ORDER BY valid_from"
                ),
                {"l": loan_id},
            ).all()
        assert [(r.valid_from.isoformat(), r.valid_to.isoformat()) for r in rows] == [
            ("2024-07-01", "2024-07-31"),
            ("2024-08-15", "2024-08-15"),
        ]
    finally:
        with etl_transaction() as conn:
            conn.execute(
                text("DELETE FROM dwh.dim_loan_version WHERE loan_id = :l"), {"l": loan_id}
            )
            conn.execute(text("DELETE FROM dwh.dim_loan WHERE loan_id = :l"), {"l": loan_id})


def test_counterparty_inn_pairing_check_rejected() -> None:
    """`CHECK ((inn_enc IS NULL) = (inn_bidx IS NULL))` — biri bo'lib, ikkinchisi bo'lmasa
    ma'lumot izlab topib bo'lmaydigan (bidx'siz) yoki shifrlanmagan qoldiqqa aylanadi."""
    code = f"CP-P{uuid.uuid4().hex[:8]}"
    with etl_transaction() as conn, pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(
            text(
                "INSERT INTO dwh.dim_counterparty (code, name, kind, inn_enc, src_system) "
                "VALUES (:c, 'X', 'supplier', '\\x00', 'test')"
            ),
            {"c": code},
        )


def test_bank_currency_format_check_rejected() -> None:
    code = f"BK-{uuid.uuid4().hex[:8]}"
    with etl_transaction() as conn, pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(
            text(
                "INSERT INTO dwh.dim_bank (code, bank_name, currency, src_system) "
                "VALUES (:c, 'X', 'usd', 'test')"
            ),
            {"c": code},
        )
