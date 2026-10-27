"""S4: АИП — obyekt × oy (reja, fakt, ochilish, КС-2, avans) va bosqichlar snapshot'i

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-25
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_investment_month", "agg_object_stages")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_investment_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      object_id integer NOT NULL,
      object_code varchar(32) NOT NULL,
      name varchar(300) NOT NULL,
      program_code varchar(32),
      work_type varchar(16) NOT NULL,
      source_name varchar(200) NOT NULL,
      commissioning_year smallint,
      total_cost numeric(20,2),
      plan {MONEY},
      fact {MONEY},
      opening {MONEY},
      physical_pct numeric(7,4),
      advance numeric(20,2),
      advance_date_id integer,
      PRIMARY KEY (build_id, branch_id, month_id, object_id)
    )
    """,
    f"""
    CREATE TABLE mart.agg_object_stages (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      object_id integer NOT NULL,
      stage_no smallint NOT NULL,
      stage_name varchar(200) NOT NULL,
      plan_date_id integer NOT NULL,
      fact_date_id integer,
      done boolean NOT NULL,
      late boolean NOT NULL,
      PRIMARY KEY (build_id, branch_id, month_id, object_id, stage_no)
    )
    """,
    f"""
    CREATE VIEW pub.agg_investment_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.object_id, a.object_code, a.name, a.program_code,
           a.work_type, a.source_name, a.commissioning_year, a.total_cost, a.plan, a.fact,
           a.opening, a.physical_pct, a.advance, a.advance_date_id
    FROM mart.agg_investment_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_object_stages WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.object_id, a.stage_no, a.stage_name, a.plan_date_id,
           a.fact_date_id, a.done, a.late
    FROM mart.agg_object_stages a WHERE a.build_id = {ACTIVE}
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
