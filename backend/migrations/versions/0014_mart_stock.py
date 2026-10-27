"""S3: ombor — oy × kategoriya snapshot'i (qiymat, minimum, yosh, oborot), belgilangan pozitsiyalar

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-25
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_stock_month", "agg_stock_positions")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_stock_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      category varchar(100) NOT NULL,
      snap_date_id integer,
      positions integer NOT NULL DEFAULT 0,
      value {MONEY},
      below_min integer NOT NULL DEFAULT 0,
      min_known integer NOT NULL DEFAULT 0,
      idle_value {MONEY},
      age_le90 {MONEY},
      age_91_180 {MONEY},
      age_181_365 {MONEY},
      age_gt365 {MONEY},
      age_unknown {MONEY},
      inflow {MONEY},
      outflow {MONEY},
      PRIMARY KEY (build_id, branch_id, month_id, category)
    )
    """,
    f"""
    CREATE TABLE mart.agg_stock_positions (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      nom_id integer NOT NULL,
      warehouse varchar(100) NOT NULL,
      snap_date_id integer NOT NULL,
      nom_code varchar(32) NOT NULL,
      name varchar(300) NOT NULL,
      category varchar(100) NOT NULL,
      unit varchar(16) NOT NULL,
      qty numeric(20,3) NOT NULL,
      min_qty numeric(20,3),
      value numeric(20,2) NOT NULL,
      last_move_date_id integer,
      age_days integer,
      below_min boolean NOT NULL,
      idle boolean NOT NULL,
      PRIMARY KEY (build_id, branch_id, month_id, nom_id, warehouse)
    )
    """,
    f"""
    CREATE VIEW pub.agg_stock_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.category, a.snap_date_id, a.positions, a.value,
           a.below_min, a.min_known, a.idle_value, a.age_le90, a.age_91_180, a.age_181_365,
           a.age_gt365, a.age_unknown, a.inflow, a.outflow
    FROM mart.agg_stock_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_stock_positions WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.nom_id, a.warehouse, a.snap_date_id, a.nom_code, a.name,
           a.category, a.unit, a.qty, a.min_qty, a.value, a.last_move_date_id, a.age_days,
           a.below_min, a.idle
    FROM mart.agg_stock_positions a WHERE a.build_id = {ACTIVE}
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
