"""S2: kreditlar — oy × kredit snapshot'i va to'lov grafigi (valyutada)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-25
"""

from alembic import op

revision = "0011"
down_revision = "0010"  # `alembic heads` boshqa bo'lsa — shu qiymatni joriy head'ga moslang
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_loan_month", "agg_loan_schedule")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_loan_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      loan_id integer NOT NULL,
      snap_date_id integer NOT NULL,
      loan_code varchar(32) NOT NULL,
      creditor varchar(200) NOT NULL,
      project varchar(300) NOT NULL,
      currency char(3) NOT NULL,
      rate numeric(8,5) NOT NULL,
      grace_until date,
      maturity date NOT NULL,
      fx_rate numeric(18,6),
      original_cur numeric(20,2) NOT NULL,
      outstanding_cur numeric(20,2) NOT NULL,
      outstanding numeric(20,2),
      PRIMARY KEY (build_id, branch_id, month_id, loan_id)
    )
    """,
    f"""
    CREATE TABLE mart.agg_loan_schedule (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      loan_id integer NOT NULL,
      month_id integer NOT NULL,
      date_id integer NOT NULL,
      principal_cur {MONEY},
      interest_cur {MONEY},
      balance_cur {MONEY},
      PRIMARY KEY (build_id, branch_id, loan_id, date_id)
    )
    """,
    f"""
    CREATE VIEW pub.agg_loan_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.loan_id, a.snap_date_id, a.loan_code, a.creditor,
           a.project, a.currency, a.rate, a.grace_until, a.maturity, a.fx_rate, a.original_cur,
           a.outstanding_cur, a.outstanding
    FROM mart.agg_loan_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_loan_schedule WITH (security_invoker = true) AS
    SELECT a.branch_id, a.loan_id, a.month_id, a.date_id, a.principal_cur, a.interest_cur,
           a.balance_cur
    FROM mart.agg_loan_schedule a WHERE a.build_id = {ACTIVE}
    """,
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
    for table in reversed(TABLES):
        op.execute(f"DROP VIEW pub.{table}")
        op.execute(f"DROP TABLE mart.{table}")
