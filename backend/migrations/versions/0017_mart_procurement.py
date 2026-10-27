"""S4: xaridlar — lotlar reyestri snapshot'i va yillik reja

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-25
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_procurement_lots", "agg_procurement_plan")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_procurement_lots (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      lot_src varchar(200) NOT NULL,
      date_id integer NOT NULL,
      lot_no varchar(64) NOT NULL,
      method varchar(32) NOT NULL,
      status varchar(32) NOT NULL,
      start_price {MONEY},
      contract_price numeric(20,2),
      days integer,
      norm_days integer,
      overdue boolean NOT NULL DEFAULT false,
      subject varchar(100) NOT NULL,
      supplier varchar(300),
      PRIMARY KEY (build_id, branch_id, lot_src)
    )
    """,
    "CREATE INDEX agg_procurement_lots_month_idx ON mart.agg_procurement_lots (build_id, month_id)",
    f"""
    CREATE TABLE mart.agg_procurement_plan (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      plan {MONEY},
      PRIMARY KEY (build_id, branch_id, month_id)
    )
    """,
    f"""
    CREATE VIEW pub.agg_procurement_lots WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.lot_src, a.date_id, a.lot_no, a.method, a.status,
           a.start_price, a.contract_price, a.days, a.norm_days, a.overdue, a.subject, a.supplier
    FROM mart.agg_procurement_lots a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_procurement_plan WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.plan
    FROM mart.agg_procurement_plan a WHERE a.build_id = {ACTIVE}
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
