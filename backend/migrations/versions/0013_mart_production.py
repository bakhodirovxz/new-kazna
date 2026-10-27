"""S3: ishlab chiqarish — oy × stansiya (quvvat, soatlar, reja) va realizatsiya

Revision ID: 0013
Revises: 0010
Create Date: 2026-09-25
"""

from alembic import op

revision = "0013"
down_revision = "0021"
branch_labels = None
depends_on = None

VOLUME = "numeric(20,3) NOT NULL DEFAULT 0"
MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_generation_month", "agg_energy_sales_month")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_generation_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      days_in_period smallint NOT NULL,
      days_in_month smallint NOT NULL,
      stations integer NOT NULL DEFAULT 0,
      capacity_mw numeric(12,2),
      capacity_hours numeric(16,2) NOT NULL DEFAULT 0,
      generation {VOLUME},
      generation_cmp {VOLUME},
      own_needs {VOLUME},
      plan {VOLUME},
      plan_full {VOLUME},
      PRIMARY KEY (build_id, branch_id, month_id)
    )
    """,
    f"""
    CREATE TABLE mart.agg_energy_sales_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      accrued {MONEY},
      paid {MONEY},
      volume {VOLUME},
      PRIMARY KEY (build_id, branch_id, month_id)
    )
    """,
    f"""
    CREATE VIEW pub.agg_generation_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.days_in_period, a.days_in_month, a.stations,
           a.capacity_mw, a.capacity_hours, a.generation, a.generation_cmp, a.own_needs, a.plan,
           a.plan_full
    FROM mart.agg_generation_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_energy_sales_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.accrued, a.paid, a.volume
    FROM mart.agg_energy_sales_month a WHERE a.build_id = {ACTIVE}
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
