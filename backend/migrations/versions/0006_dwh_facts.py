"""dwh faktlari: partitsiyalar, indekslar, RLS, idempotentlik kalitlari

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-24

Partitsiyalangan jadvalda UNIQUE partitsiya kalitini (date_id) o'z ichiga olishi SHART
(PostgreSQL cheklovi). Shuning uchun partitsiyalangan faktlarda idempotentlik kaliti
(src_system, doc_type, src_id, date_id). Manbada hujjat sanasi o'zgarsa, loader eski sanadagi
nusxani (src_system, doc_type, src_id) indeksi bo'yicha oldindan o'chiradi (app/etl/merge.py).
"""

from dataclasses import dataclass, field

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

MONEY = "numeric(20,2)"
VOLUME = "numeric(20,3)"
FK_TARGETS = {
    "branch_id": "dim_branch", "item_id": "dim_item", "cp_id": "dim_counterparty",
    "contract_id": "dim_contract", "bank_id": "dim_bank", "nom_id": "dim_nomenclature",
    "object_id": "dim_object", "loan_id": "dim_loan", "pos_id": "dim_position",
    "source_id": "dim_source",
}
PO_STATUSES = (
    "'черновик', 'на согласовании', 'утверждено', 'отправлено в банк', 'исполнено', 'отклонено'"
)


@dataclass(frozen=True)
class Fact:
    name: str
    fks: dict[str, bool]  # ustun -> NOT NULL
    measures: tuple[str, ...]
    partition: str | None = None  # 'month' | 'year'
    brin: bool = False
    partial: tuple[tuple[str, str], ...] = field(default=())  # (ustunlar, WHERE)


FACTS = (
    Fact("fact_cashflow",
         {"branch_id": True, "item_id": True, "cp_id": False, "contract_id": False,
          "bank_id": False},
         ("direction varchar(3) NOT NULL CHECK (direction IN ('in', 'out'))",
          f"amount {MONEY} NOT NULL CHECK (amount >= 0)",
          "gl_account varchar(8)"),
         partition="month", brin=True),
    Fact("fact_balance", {"branch_id": True, "bank_id": True},
         (f"balance {MONEY} NOT NULL",), partition="year"),
    Fact("fact_payment_plan", {"branch_id": True, "item_id": True},
         (f"amount {MONEY} NOT NULL CHECK (amount >= 0)",)),
    Fact("fact_payment_order",
         {"branch_id": True, "item_id": True, "cp_id": False, "bank_id": False},
         (f"amount {MONEY} NOT NULL CHECK (amount >= 0)",
          f"status varchar(24) NOT NULL CHECK (status IN ({PO_STATUSES}))",
          "status_date_id integer"),
         partition="month",
         partial=(("branch_id, date_id", "status IN ('на согласовании', 'утверждено')"),)),
    Fact("fact_debt", {"branch_id": True, "contract_id": True, "cp_id": False},
         (f"receivable {MONEY} NOT NULL DEFAULT 0", f"payable {MONEY} NOT NULL DEFAULT 0",
          f"overdue {MONEY} NOT NULL DEFAULT 0",
          "overdue_days integer NOT NULL DEFAULT 0 CHECK (overdue_days >= 0)"),
         partition="year", partial=(("branch_id", "overdue_days > 0"),)),
    Fact("fact_generation", {"branch_id": True},
         (f"generation {VOLUME} NOT NULL CHECK (generation >= 0)",
          f"own_needs {VOLUME} NOT NULL DEFAULT 0", f"supply {VOLUME} NOT NULL DEFAULT 0",
          f"plan {VOLUME}", "work_hours numeric(6,2)"),
         partition="year"),
    Fact("fact_energy_sales", {"branch_id": True, "cp_id": True},
         (f"accrued {MONEY} NOT NULL DEFAULT 0", f"paid {MONEY} NOT NULL DEFAULT 0",
          f"volume {VOLUME} NOT NULL DEFAULT 0")),
    Fact("fact_procurement", {"branch_id": True, "nom_id": False, "cp_id": False},
         ("lot_no varchar(64) NOT NULL", "method varchar(32) NOT NULL",
          "status varchar(32) NOT NULL", f"start_price {MONEY} NOT NULL",
          f"contract_price {MONEY}", "procedure_days integer"),
         partial=(("branch_id", "status IN ('объявлен', 'на оценке')"),)),
    Fact("fact_stock", {"branch_id": True, "nom_id": True},
         ("warehouse varchar(100) NOT NULL", f"qty {VOLUME} NOT NULL",
          f"value {MONEY} NOT NULL", f"min_qty {VOLUME}", "last_move_date_id integer"),
         partition="year"),
    Fact("fact_stock_move", {"branch_id": True, "nom_id": True},
         ("direction varchar(3) NOT NULL CHECK (direction IN ('in', 'out'))",
          f"qty {VOLUME} NOT NULL", f"value {MONEY} NOT NULL"),
         partition="year", brin=True),
    Fact("fact_investment", {"branch_id": True, "object_id": True, "source_id": False},
         (f"plan {MONEY} NOT NULL DEFAULT 0", f"fact {MONEY} NOT NULL DEFAULT 0",
          "physical_pct numeric(7,4)", f"advance {MONEY} NOT NULL DEFAULT 0",
          "advance_date_id integer")),
    # Kredit grafigi summalari kredit valyutasida (mln); so'mga fx_rate bilan o'giriladi.
    Fact("fact_loan_schedule", {"branch_id": True, "loan_id": True},
         (f"principal {MONEY} NOT NULL DEFAULT 0", f"interest {MONEY} NOT NULL DEFAULT 0",
          f"balance {MONEY} NOT NULL DEFAULT 0")),
    Fact("fact_hr", {"branch_id": True, "pos_id": True},
         ("headcount_plan numeric(10,1) NOT NULL DEFAULT 0",
          "headcount_fact numeric(10,1) NOT NULL DEFAULT 0",
          f"payroll {MONEY} NOT NULL DEFAULT 0", "hired integer NOT NULL DEFAULT 0",
          "fired integer NOT NULL DEFAULT 0",
          "overtime_hours numeric(12,1) NOT NULL DEFAULT 0")),
    Fact("fact_target_funds", {"branch_id": True, "source_id": True, "object_id": False},
         (f"allocated {MONEY} NOT NULL DEFAULT 0", f"used {MONEY} NOT NULL DEFAULT 0")),
)


def _create_statements(f: Fact) -> list[str]:
    cols = ["date_id integer NOT NULL REFERENCES dwh.dim_date (date_id) "
            "DEFERRABLE INITIALLY DEFERRED"]
    for col, required in f.fks.items():
        null = " NOT NULL" if required else ""
        cols.append(f"{col} integer{null} REFERENCES dwh.{FK_TARGETS[col]} ({col}) "
                    "DEFERRABLE INITIALLY DEFERRED")
    cols += list(f.measures)
    cols += [
        "load_id bigint NOT NULL",
        "src_system varchar(32) NOT NULL",
        "doc_type varchar(32) NOT NULL",
        "src_id varchar(128) NOT NULL",
        "updated_at timestamptz NOT NULL DEFAULT now()",
    ]
    key = "src_system, doc_type, src_id" + (", date_id" if f.partition else "")
    cols.append(f"CONSTRAINT {f.name}_src_uq UNIQUE ({key})")
    part = " PARTITION BY RANGE (date_id)" if f.partition else ""
    out = [f"CREATE TABLE dwh.{f.name} (\n  " + ",\n  ".join(cols) + f"\n){part}"]

    # TZ majburiy indekslari + har FK ustunida B-tree (spec 4.5).
    indexes: list[tuple[str, str | None]] = [("date_id, branch_id", None)]
    if "item_id" in f.fks:
        indexes += [("branch_id, item_id", None), ("item_id", None)]
    else:
        indexes.append(("branch_id", None))
    indexes += [(col, None) for col in f.fks if col not in ("branch_id", "item_id")]
    if f.partition:
        indexes.append(("src_system, doc_type, src_id", None))
    indexes += list(f.partial)
    for columns, where in indexes:
        suffix = "_p" if where else ""
        name = f"{f.name}_{columns.replace(', ', '_')}{suffix}_idx"
        where_sql = f" WHERE {where}" if where else ""
        out.append(f"CREATE INDEX {name} ON dwh.{f.name} ({columns}){where_sql}")
    if f.brin:
        out.append(f"CREATE INDEX {f.name}_date_brin ON dwh.{f.name} USING brin (date_id)")

    out += [
        f"ALTER TABLE dwh.{f.name} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE dwh.{f.name} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY branch_scope ON dwh.{f.name} USING (core.rls_branch_ok(branch_id)) "
        "WITH CHECK (core.rls_branch_ok(branch_id))",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON dwh.{f.name} TO ugk_etl",
    ]
    return out


# A3.1: SET search_path = pg_catalog, pg_temp (Plan 1 SECURITY DEFINER konvensiyasi,
# 0004_audit.py:88,140,184,199) — dwh emas. pg_temp ro'yxatda bo'lmasa, u implicit ravishda
# birinchi qidiriladi; ikkala funksiya tanasidagi har bir munosabat allaqachon `dwh.`
# prefiksi bilan yoki pg_catalog'da.
ENSURE_PARTITIONS = """
CREATE FUNCTION dwh.ensure_partitions(p_table text, p_from date, p_to date) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  grain text;
  cur date;
  nxt date;
  part text;
  created integer := 0;
BEGIN
  grain := CASE p_table
    WHEN 'fact_cashflow' THEN 'month' WHEN 'fact_payment_order' THEN 'month'
    WHEN 'fact_balance' THEN 'year' WHEN 'fact_debt' THEN 'year'
    WHEN 'fact_generation' THEN 'year' WHEN 'fact_stock' THEN 'year'
    WHEN 'fact_stock_move' THEN 'year' END;
  IF grain IS NULL THEN
    RAISE EXCEPTION 'partitsiyalanmagan jadval: %', p_table;
  END IF;
  -- Worker va ETL bir vaqtda bir xil partitsiyani yaratmasin.
  PERFORM pg_advisory_xact_lock(hashtext('ugk_partitions'));
  cur := date_trunc(grain, p_from)::date;
  WHILE cur <= p_to LOOP
    nxt := (cur + CASE grain WHEN 'month' THEN interval '1 month'
                             ELSE interval '1 year' END)::date;
    part := p_table || '_p' || to_char(cur, CASE grain WHEN 'month' THEN 'YYYYMM'
                                                       ELSE 'YYYY' END);
    IF to_regclass('dwh.' || part) IS NULL THEN
      EXECUTE format('CREATE TABLE dwh.%I PARTITION OF dwh.%I FOR VALUES FROM (%s) TO (%s)',
                     part, p_table, to_char(cur, 'YYYYMMDD'), to_char(nxt, 'YYYYMMDD'));
      created := created + 1;
    END IF;
    cur := nxt;
  END LOOP;
  RETURN created;
END
$$
"""

DROP_OLD_PARTITIONS = """
CREATE FUNCTION dwh.drop_old_partitions(p_keep_years integer) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  cutoff integer;
  dropped integer := 0;
  r record;
  suffix text;
  upper_bound integer;
BEGIN
  IF p_keep_years < 1 THEN
    RAISE EXCEPTION 'p_keep_years kamida 1 bo''lishi kerak';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('ugk_partitions'));
  cutoff := to_char(date_trunc('month', now() AT TIME ZONE 'UTC')
                    - make_interval(years => p_keep_years), 'YYYYMMDD')::integer;
  FOR r IN
    SELECT c.relname AS part, p.relname AS parent
    FROM pg_inherits i
    JOIN pg_class c ON c.oid = i.inhrelid
    JOIN pg_class p ON p.oid = i.inhparent
    JOIN pg_namespace n ON n.oid = p.relnamespace
    WHERE n.nspname = 'dwh' AND c.relname ~ '^fact_[a-z_]+_p[0-9]{4}([0-9]{2})?$'
  LOOP
    suffix := substring(r.part FROM '_p([0-9]+)$');
    IF length(suffix) = 6 THEN
      upper_bound := to_char(to_date(suffix, 'YYYYMM') + interval '1 month', 'YYYYMMDD')::integer;
    ELSE
      upper_bound := to_char(to_date(suffix, 'YYYY') + interval '1 year', 'YYYYMMDD')::integer;
    END IF;
    IF upper_bound <= cutoff THEN
      EXECUTE format('ALTER TABLE dwh.%I DETACH PARTITION dwh.%I', r.parent, r.part);
      EXECUTE format('DROP TABLE dwh.%I', r.part);
      dropped := dropped + 1;
    END IF;
  END LOOP;
  RETURN dropped;
END
$$
"""


def upgrade() -> None:
    for fact in FACTS:
        for statement in _create_statements(fact):
            op.execute(statement)
    op.execute(ENSURE_PARTITIONS)
    op.execute(DROP_OLD_PARTITIONS)
    for fn in ("ensure_partitions(text, date, date)", "drop_old_partitions(integer)"):
        op.execute(f"REVOKE ALL ON FUNCTION dwh.{fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION dwh.{fn} TO ugk_etl")
    for fact in FACTS:
        if fact.partition:
            op.execute(
                f"SELECT dwh.ensure_partitions('{fact.name}', date_trunc('month', now())::date, "
                "(now() + interval '3 months')::date)"
            )


def downgrade() -> None:
    op.execute("DROP FUNCTION dwh.drop_old_partitions(integer)")
    op.execute("DROP FUNCTION dwh.ensure_partitions(text, date, date)")
    for fact in reversed(FACTS):
        op.execute(f"DROP TABLE dwh.{fact.name}")
