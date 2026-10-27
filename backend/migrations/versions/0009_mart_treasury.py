"""S1: banklar kesimidagi oqim/qoldiq, to'lov topshiriqlari holatlari, maqsadli mablag'lar

Revision ID: 0009
Revises: 0008a
Create Date: 2026-09-25
"""

from alembic import op

revision = "0009"
down_revision = "0008a"
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_cash_bank_month", "agg_payment_orders_month", "agg_target_funds_month")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_cash_bank_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      bank_name varchar(200) NOT NULL,
      inflow {MONEY},
      outflow {MONEY},
      closing_balance numeric(20,2),
      closing_cmp numeric(20,2),
      PRIMARY KEY (build_id, branch_id, month_id, bank_name)
    )
    """,
    f"""
    CREATE TABLE mart.agg_payment_orders_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      status varchar(24) NOT NULL,
      doc_count integer NOT NULL,
      amount {MONEY},
      PRIMARY KEY (build_id, branch_id, month_id, status)
    )
    """,
    f"""
    CREATE TABLE mart.agg_target_funds_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      source_id integer NOT NULL,
      source_name varchar(200) NOT NULL,
      allocated {MONEY},
      used {MONEY},
      PRIMARY KEY (build_id, branch_id, month_id, source_id)
    )
    """,
    f"""
    CREATE VIEW pub.agg_cash_bank_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.bank_name, a.inflow, a.outflow, a.closing_balance,
           a.closing_cmp
    FROM mart.agg_cash_bank_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_payment_orders_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.status, a.doc_count, a.amount
    FROM mart.agg_payment_orders_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_target_funds_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.source_id, a.source_name, a.allocated, a.used
    FROM mart.agg_target_funds_month a WHERE a.build_id = {ACTIVE}
    """,
    # Hisob × oy bo'yicha oxirgi qoldiqni LATERAL ... LIMIT 1 bilan tez topish uchun.
    "CREATE INDEX fact_balance_bank_id_date_id_idx ON dwh.fact_balance (bank_id, date_id)",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        op.execute(f"ALTER TABLE mart.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE mart.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY branch_scope ON mart.{table} USING (core.rls_branch_ok(branch_id)) "
                   "WITH CHECK (core.rls_branch_ok(branch_id))")
        op.execute(f"GRANT SELECT ON mart.{table} TO ugk_app")
        op.execute(f"GRANT SELECT, INSERT, DELETE ON mart.{table} TO ugk_etl")
        op.execute(f"GRANT SELECT ON pub.{table} TO ugk_app")


def downgrade() -> None:
    op.execute("DROP INDEX dwh.fact_balance_bank_id_date_id_idx")
    for table in reversed(TABLES):
        op.execute(f"DROP VIEW pub.{table}")
        op.execute(f"DROP TABLE mart.{table}")
