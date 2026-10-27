"""S3: jonli quvvat snapshot'lari (treplex.uz) va pub.power_latest

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-25

Runner/build'dan tashqarida (spec 3.2, qaror 4): har 10 daqiqada worker yozadi, UI eng oxirgi
snapshot'ni o'qiydi. RLS — filial bo'yicha, view security_invoker.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE dwh.fact_power_snapshot (
      snap_at timestamptz NOT NULL,
      station varchar(40) NOT NULL,
      station_name varchar(200) NOT NULL,
      cascade_name varchar(200) NOT NULL,
      branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id),
      power_mw numeric(10,4) NOT NULL CHECK (power_mw >= 0),
      units_working smallint NOT NULL DEFAULT 0 CHECK (units_working >= 0),
      units_reserve smallint NOT NULL DEFAULT 0 CHECK (units_reserve >= 0),
      units_repair smallint NOT NULL DEFAULT 0 CHECK (units_repair >= 0),
      source_date varchar(40),
      loaded_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (station, snap_at)
    )
    """,
    "CREATE INDEX fact_power_snapshot_snap_idx ON dwh.fact_power_snapshot (snap_at DESC)",
    "CREATE INDEX fact_power_snapshot_branch_idx ON dwh.fact_power_snapshot "
    "(branch_id, snap_at DESC)",
    "ALTER TABLE dwh.fact_power_snapshot ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE dwh.fact_power_snapshot FORCE ROW LEVEL SECURITY",
    "CREATE POLICY branch_scope ON dwh.fact_power_snapshot USING (core.rls_branch_ok(branch_id)) "
    "WITH CHECK (core.rls_branch_ok(branch_id))",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON dwh.fact_power_snapshot TO ugk_etl",
    "GRANT SELECT ON dwh.fact_power_snapshot TO ugk_app",
    """
    CREATE VIEW pub.power_latest WITH (security_invoker = true) AS
    SELECT p.snap_at, p.station, p.station_name, p.cascade_name, p.branch_id, p.power_mw,
           p.units_working, p.units_reserve, p.units_repair, p.source_date
    FROM dwh.fact_power_snapshot p
    WHERE p.snap_at = (SELECT max(x.snap_at) FROM dwh.fact_power_snapshot x)
    """,
    "GRANT SELECT ON pub.power_latest TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP VIEW pub.power_latest")
    op.execute("DROP TABLE dwh.fact_power_snapshot")
