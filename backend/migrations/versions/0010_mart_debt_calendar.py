"""S1: shartnomalar qarzdorligi (snapshot), oylik qarzdorlik, 14 kunlik to'lov kalendari

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-25
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_debt_contracts", "agg_debt_month", "agg_calendar_day")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_debt_contracts (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      contract_id integer NOT NULL,
      contract_number varchar(64) NOT NULL,
      cp_name varchar(300) NOT NULL,
      kind varchar(10) NOT NULL CHECK (kind IN ('receivable', 'payable')),
      end_date date,
      receivable {MONEY},
      payable {MONEY},
      overdue {MONEY},
      overdue_days integer NOT NULL DEFAULT 0,
      PRIMARY KEY (build_id, branch_id, month_id, contract_id)
    )
    """,
    f"""
    CREATE TABLE mart.agg_debt_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      receivable {MONEY},
      payable {MONEY},
      overdue_receivable {MONEY},
      overdue_payable {MONEY},
      contracts integer NOT NULL DEFAULT 0,
      PRIMARY KEY (build_id, branch_id, month_id)
    )
    """,
    f"""
    CREATE TABLE mart.agg_calendar_day (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      as_of_id integer NOT NULL,
      date_id integer NOT NULL,
      kind varchar(10) NOT NULL CHECK (kind IN ('taxes', 'salary', 'loans', 'contracts')),
      amount {MONEY},
      PRIMARY KEY (build_id, branch_id, date_id, kind)
    )
    """,
    f"""
    CREATE VIEW pub.agg_debt_contracts WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.contract_id, a.contract_number, a.cp_name, a.kind,
           a.end_date, a.receivable, a.payable, a.overdue, a.overdue_days
    FROM mart.agg_debt_contracts a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_debt_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.receivable, a.payable, a.overdue_receivable,
           a.overdue_payable, a.contracts
    FROM mart.agg_debt_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_calendar_day WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.as_of_id, a.date_id, a.kind, a.amount
    FROM mart.agg_calendar_day a WHERE a.build_id = {ACTIVE}
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
