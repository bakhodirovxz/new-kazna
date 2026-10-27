"""S4: kadrlar — filial × oy × toifa (штат, факт, qabul, bo'shatish, ish vaqtidan tashqari soatlar)

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-25

Faqat agregatlar — ФИО va boshqa shaxsiy ma'lumot ustunlari yo'q (TZ 9).
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"


def upgrade() -> None:
    op.execute(f"""
    CREATE TABLE mart.agg_hr_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      category varchar(100) NOT NULL,
      headcount_plan numeric(10,1) NOT NULL DEFAULT 0,
      headcount_fact numeric(10,1) NOT NULL DEFAULT 0,
      hired integer NOT NULL DEFAULT 0,
      fired integer NOT NULL DEFAULT 0,
      overtime_hours numeric(12,1) NOT NULL DEFAULT 0,
      PRIMARY KEY (build_id, branch_id, month_id, category)
    )
    """)
    op.execute(f"""
    CREATE VIEW pub.agg_hr_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.category, a.headcount_plan, a.headcount_fact, a.hired,
           a.fired, a.overtime_hours
    FROM mart.agg_hr_month a WHERE a.build_id = {ACTIVE}
    """)
    op.execute("ALTER TABLE mart.agg_hr_month ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mart.agg_hr_month FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY branch_scope ON mart.agg_hr_month USING (core.rls_branch_ok(branch_id)) "
               "WITH CHECK (core.rls_branch_ok(branch_id))")
    op.execute("GRANT SELECT ON mart.agg_hr_month TO ugk_app")
    op.execute("GRANT SELECT, INSERT, DELETE ON mart.agg_hr_month TO ugk_etl")
    op.execute("GRANT SELECT ON pub.agg_hr_month TO ugk_app")


def downgrade() -> None:
    op.execute("DROP VIEW pub.agg_hr_month")
    op.execute("DROP TABLE mart.agg_hr_month")
