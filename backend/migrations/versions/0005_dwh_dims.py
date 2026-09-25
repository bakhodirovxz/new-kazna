"""dwh o'lchovlari, fx_rate, filiallar seed'i, position_branches FK

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-24
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TECH = (
    "load_id bigint, src_system varchar(32) NOT NULL DEFAULT 'seed', "
    "updated_at timestamptz NOT NULL DEFAULT now()"
)

# Prototip "reference" + "production data" (CAP). id'lar qat'iy: 1 — HQ, 2..16 — stansiyalar.
# Kodlar, INN va koordinatalar taxminiy — TZ ochiq savoli hal bo'lganda 1C'dan yangilanadi.
BRANCHES = [
    (1, "UGE-01", "АО «Узбекгидроэнерго»", "Узбекгидроэнерго", "head", None, 41.3111, 69.2797),
    (2, "UGE-02", "Чарвакская ГЭС", "Чарвак", "ges", 666, 41.6260, 70.0290),
    (3, "UGE-03", "Каскад Чирчикских ГЭС", "Чирчик", "cascade", 190, 41.4700, 69.5800),
    (4, "UGE-04", "Андижанская ГЭС", "Андижан", "ges", 190, 40.7700, 73.0800),
    (5, "UGE-05", "Фархадская ГЭС", "Фархад", "ges", 126, 40.2300, 69.1300),
    (6, "UGE-06", "Туямуюнская ГЭС", "Туямуюн", "ges", 150, 41.2400, 61.4100),
    (7, "UGE-07", "Каскад Кадырьинских ГЭС", "Кадырья", "cascade", 44, 41.3300, 69.4200),
    (8, "UGE-08", "Ходжикентская ГЭС", "Ходжикент", "ges", 165, 41.5700, 69.8900),
    (9, "UGE-09", "Каскад Ташкентских ГЭС", "Ташкент", "cascade", 29, 41.2900, 69.2500),
    (10, "UGE-10", "Каскад Самаркандских ГЭС", "Самарканд", "cascade", 36, 39.6600, 66.9800),
    (11, "UGE-11", "Газалкентская ГЭС", "Газалкент", "ges", 120, 41.5600, 69.7700),
    (12, "UGE-12", "Каскад Нижнебозсуйских ГЭС", "Нижний Бозсу", "cascade", 50, 41.1200, 69.2000),
    (13, "UGE-13", "Тупалангская ГЭС", "Тупаланг", "ges", 175, 38.5200, 67.9200),
    (14, "UGE-14", "Каскад Шахриханских ГЭС", "Шахрихан", "cascade", 20, 40.7100, 72.0500),
    (15, "UGE-15", "Гиссаракская ГЭС", "Гиссарак", "ges", 45, 38.9600, 67.2600),
    (16, "UGE-16", "Ахангаранская ГЭС", "Ахангаран", "ges", 21, 40.9500, 70.0700),
]
# ETL statyasiz yozuvlarni shu statyalarga yo'naltiradi (spec 5.3, 3-tekshiruv).
SYSTEM_ITEMS = [
    ("PKM54-I06", "Прочие поступления", "operating", "in", 106),
    ("PKM54-O09", "Прочие операционные расходы", "operating", "out", 209),
]
DIM_TABLES = (
    "dim_date", "dim_branch", "dim_branch_version", "dim_item", "dim_counterparty", "dim_bank",
    "dim_nomenclature", "dim_source", "dim_object", "dim_contract", "dim_loan",
    "dim_loan_version", "dim_position", "fx_rate",
)
RLS_TABLES = ("dim_branch", "dim_branch_version", "dim_contract", "dim_loan")


def _sql_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def _row(values: tuple[object, ...]) -> str:
    return "(" + ", ".join(_sql_value(v) for v in values) + ")"


def upgrade() -> None:
    # SCD-2 (branch/loan versiyalari) davr-qoplanish EXCLUDE'lari uchun (fix r1). btree_gist
    # PG16'da "trusted" — database egasi (`ugk_migrator`, superuser emas) ham o'rnatishi mumkin.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        CREATE TABLE dwh.dim_date (
          date_id integer PRIMARY KEY,
          date date NOT NULL UNIQUE,
          year smallint NOT NULL,
          quarter smallint NOT NULL,
          month smallint NOT NULL,
          month_id integer NOT NULL,
          day smallint NOT NULL,
          iso_dow smallint NOT NULL,
          is_workday boolean NOT NULL
        )
        """
    )
    # Ish kuni = dushanba–juma; bayramlar ishlab chiqarish kalendari bilan keyingi spec'da.
    op.execute(
        """
        INSERT INTO dwh.dim_date
        SELECT to_char(g.d, 'YYYYMMDD')::int, g.d::date, extract(year FROM g.d),
               extract(quarter FROM g.d), extract(month FROM g.d), to_char(g.d, 'YYYYMM')::int,
               extract(day FROM g.d), extract(isodow FROM g.d), extract(isodow FROM g.d) < 6
        FROM generate_series(date '2015-01-01', date '2040-12-31', interval '1 day') AS g(d)
        """
    )
    op.execute("CREATE INDEX dim_date_month_idx ON dwh.dim_date (month_id)")
    op.execute(
        f"""
        CREATE TABLE dwh.dim_branch (
          branch_id serial PRIMARY KEY CHECK (branch_id > 0),
          code varchar(32) NOT NULL UNIQUE,
          name varchar(200) NOT NULL,
          short_name varchar(100) NOT NULL,
          inn varchar(9),
          kind varchar(8) NOT NULL CHECK (kind IN ('head', 'ges', 'cascade')),
          capacity_mw numeric(10,2),
          lat numeric(9,6),
          lon numeric(9,6),
          sort_order smallint NOT NULL DEFAULT 0,
          {TECH}
        )
        """
    )
    op.execute(
        """
        CREATE TABLE dwh.dim_branch_version (
          branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id),
          capacity_mw numeric(10,2),
          valid_from date NOT NULL,
          valid_to date,
          is_current boolean NOT NULL,
          PRIMARY KEY (branch_id, valid_from),
          CHECK (is_current = (valid_to IS NULL)),
          CHECK (valid_to IS NULL OR valid_to >= valid_from),
          -- Fix r2: valid_to INKLYUZIV (reja: yopish valid_to = as_of - 1 deb belgilaydi,
          -- join'lar d.date <= v.valid_to) — daterange '[]' bilan ikkala chegara ham
          -- kiritiladi, bir kunlik versiya (valid_from = valid_to) qonuniy bo'ladi.
          EXCLUDE USING gist (
            branch_id WITH =,
            daterange(valid_from, coalesce(valid_to, 'infinity'::date), '[]') WITH &&
          )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX dim_branch_version_current ON dwh.dim_branch_version (branch_id) "
        "WHERE is_current"
    )
    values = ", ".join(
        _row((bid, code, name, short, f"2011{bid:05d}", kind, cap, lat, lon, bid))
        for bid, code, name, short, kind, cap, lat, lon in BRANCHES
    )
    op.execute(
        "INSERT INTO dwh.dim_branch (branch_id, code, name, short_name, inn, kind, capacity_mw, "
        f"lat, lon, sort_order) VALUES {values}"
    )
    op.execute("SELECT setval('dwh.dim_branch_branch_id_seq', 16)")
    op.execute(
        "INSERT INTO dwh.dim_branch_version (branch_id, capacity_mw, valid_from, is_current) "
        "SELECT branch_id, capacity_mw, date '2000-01-01', true FROM dwh.dim_branch"
    )
    op.execute(
        f"""
        CREATE TABLE dwh.dim_item (
          item_id serial PRIMARY KEY,
          code varchar(32) NOT NULL UNIQUE,
          name varchar(300) NOT NULL,
          activity varchar(12) NOT NULL
            CHECK (activity IN ('centralized', 'operating', 'investing')),
          direction varchar(3) NOT NULL CHECK (direction IN ('in', 'out')),
          sort_order smallint NOT NULL DEFAULT 0,
          {TECH}
        )
        """
    )
    items = ", ".join(_row(row) for row in SYSTEM_ITEMS)
    op.execute(
        f"INSERT INTO dwh.dim_item (code, name, activity, direction, sort_order) VALUES {items}"
    )
    op.execute(
        f"""
        CREATE TABLE dwh.dim_counterparty (
          cp_id serial PRIMARY KEY,
          code varchar(32) NOT NULL UNIQUE,
          name varchar(300) NOT NULL,
          kind varchar(8) NOT NULL
            CHECK (kind IN ('supplier', 'buyer', 'bank', 'budget', 'ifi', 'other')),
          inn_enc bytea,
          inn_bidx bytea,
          CHECK ((inn_enc IS NULL) = (inn_bidx IS NULL)),
          {TECH}
        )
        """
    )
    op.execute("CREATE INDEX dim_counterparty_inn_bidx_idx ON dwh.dim_counterparty (inn_bidx)")
    op.execute(
        f"""
        CREATE TABLE dwh.dim_bank (
          bank_id serial PRIMARY KEY,
          code varchar(32) NOT NULL UNIQUE,
          bank_name varchar(200) NOT NULL,
          account_enc bytea,
          account_bidx bytea,
          currency char(3) NOT NULL DEFAULT 'UZS' CHECK (currency ~ '^[A-Z]{{3}}$'),
          CHECK ((account_enc IS NULL) = (account_bidx IS NULL)),
          {TECH}
        )
        """
    )
    op.execute("CREATE INDEX dim_bank_account_bidx_idx ON dwh.dim_bank (account_bidx)")
    op.execute(
        f"""
        CREATE TABLE dwh.dim_nomenclature (
          nom_id serial PRIMARY KEY,
          code varchar(32) NOT NULL UNIQUE,
          name varchar(300) NOT NULL,
          category varchar(100) NOT NULL,
          unit varchar(16) NOT NULL,
          enbt_code varchar(32),
          {TECH}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE dwh.dim_source (
          source_id serial PRIMARY KEY,
          code varchar(32) NOT NULL UNIQUE,
          name varchar(200) NOT NULL,
          kind varchar(8) NOT NULL CHECK (kind IN ('budget', 'ifi', 'bank', 'own')),
          {TECH}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE dwh.dim_object (
          object_id serial PRIMARY KEY,
          code varchar(32) NOT NULL UNIQUE,
          name varchar(300) NOT NULL,
          program_code varchar(32),
          work_type varchar(16) NOT NULL
            CHECK (work_type IN ('new', 'reconstruction', 'modernization')),
          source_id integer REFERENCES dwh.dim_source (source_id),
          commissioning_year smallint,
          total_cost numeric(20,2),
          {TECH}
        )
        """
    )
    op.execute("CREATE INDEX dim_object_source_idx ON dwh.dim_object (source_id)")
    op.execute(
        f"""
        CREATE TABLE dwh.dim_contract (
          contract_id serial PRIMARY KEY,
          code varchar(64) NOT NULL UNIQUE,
          number varchar(64) NOT NULL,
          contract_date date NOT NULL,
          cp_id integer NOT NULL REFERENCES dwh.dim_counterparty (cp_id),
          branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id),
          amount numeric(20,2) NOT NULL,
          end_date date,
          object_id integer REFERENCES dwh.dim_object (object_id),
          kind varchar(10) NOT NULL CHECK (kind IN ('receivable', 'payable')),
          {TECH}
        )
        """
    )
    for col in ("cp_id", "branch_id", "object_id"):
        op.execute(f"CREATE INDEX dim_contract_{col}_idx ON dwh.dim_contract ({col})")
    op.execute(
        f"""
        CREATE TABLE dwh.dim_loan (
          loan_id serial PRIMARY KEY,
          code varchar(32) NOT NULL UNIQUE,
          creditor varchar(200) NOT NULL,
          project varchar(300) NOT NULL,
          currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{{3}}$'),
          rate numeric(8,5) NOT NULL,
          grace_until date,
          maturity date NOT NULL,
          amount_uzs numeric(20,2) NOT NULL,
          branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id),
          {TECH}
        )
        """
    )
    op.execute("CREATE INDEX dim_loan_branch_idx ON dwh.dim_loan (branch_id)")
    op.execute(
        """
        CREATE TABLE dwh.dim_loan_version (
          loan_id integer NOT NULL REFERENCES dwh.dim_loan (loan_id),
          rate numeric(8,5),
          valid_from date NOT NULL,
          valid_to date,
          is_current boolean NOT NULL,
          PRIMARY KEY (loan_id, valid_from),
          CHECK (is_current = (valid_to IS NULL)),
          CHECK (valid_to IS NULL OR valid_to >= valid_from),
          -- Fix r2: valid_to INKLYUZIV — dim_branch_version'dagi bilan bir xil sabab.
          EXCLUDE USING gist (
            loan_id WITH =,
            daterange(valid_from, coalesce(valid_to, 'infinity'::date), '[]') WITH &&
          )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX dim_loan_version_current ON dwh.dim_loan_version (loan_id) "
        "WHERE is_current"
    )
    op.execute(
        f"""
        CREATE TABLE dwh.dim_position (
          pos_id serial PRIMARY KEY,
          code varchar(32) NOT NULL UNIQUE,
          category varchar(100) NOT NULL,
          department varchar(200) NOT NULL,
          {TECH}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE dwh.fx_rate (
          currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{{3}}$'),
          date_id integer NOT NULL REFERENCES dwh.dim_date (date_id),
          rate numeric(18,6) NOT NULL CHECK (rate > 0),
          {TECH},
          PRIMARY KEY (currency, date_id)
        )
        """
    )
    op.execute("CREATE INDEX fx_rate_date_idx ON dwh.fx_rate (date_id)")
    # RLS seed'dan keyin yoqiladi: FORCE jadval egasini ham cheklaydi.
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE dwh.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE dwh.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY branch_scope ON dwh.{table} USING (core.rls_branch_ok(branch_id)) "
            "WITH CHECK (core.rls_branch_ok(branch_id))"
        )
    tables = ", ".join(f"dwh.{t}" for t in DIM_TABLES)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tables} TO ugk_etl")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA dwh TO ugk_etl")
    # ugk_app: faqat filiallar/statyalar ro'yxati (pub view'lar, admin filial tekshiruvi).
    # Fix r1 (I1): dwh.dim_counterparty.inn_enc / dwh.dim_bank.account_enc'ga (yoki boshqa
    # ustuniga) ugk_app'ning HECH QANDAY huquqi yo'q — internetga qaragan, keyring'ni
    # ushlab turadigan ulanish shifrlangan rekvizitlarni o'qiy/yoza olmasligi kerak. Ularni
    # qayta shifrlash faqat operator CLI'da (`rotate-key`, migrator ulanishi) bajariladi —
    # app.core.reencrypt.EncryptedColumn.role'ga qarang.
    op.execute("GRANT USAGE ON SCHEMA dwh TO ugk_app")
    op.execute("GRANT SELECT ON dwh.dim_branch, dwh.dim_item TO ugk_app")
    op.execute(
        "ALTER TABLE core.position_branches ADD CONSTRAINT position_branches_branch_fk "
        "FOREIGN KEY (branch_id) REFERENCES dwh.dim_branch (branch_id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE core.position_branches DROP CONSTRAINT position_branches_branch_fk")
    op.execute("REVOKE USAGE ON SCHEMA dwh FROM ugk_app")
    for table in reversed(DIM_TABLES):
        op.execute(f"DROP TABLE dwh.{table}")
