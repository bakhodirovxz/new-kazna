"""Kadrlar: kunlik davomat (HR API /directory/attendance) va pub.attendance_daily

Revision ID: 0025
Revises: 0024m
Create Date: 2026-10-28

Runner/build'dan tashqarida (jonli quvvat kabi): worker kun x filial x holat bo'yicha
agregatlarni yozadi. F.I.Sh. saqlanmaydi. RLS - filial bo'yicha, view security_invoker.
"""

from alembic import op

revision = "0025"
down_revision = "0024m"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE dwh.fact_attendance (
      att_date date NOT NULL,
      branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id),
      status_code varchar(40) NOT NULL,
      status_label varchar(120) NOT NULL,
      status_kind varchar(24) NOT NULL,
      employees integer NOT NULL CHECK (employees >= 0),
      person_days integer NOT NULL CHECK (person_days >= 0),
      branch_employees integer NOT NULL CHECK (branch_employees >= 0),
      generated_at timestamptz NOT NULL,
      loaded_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (att_date, branch_id, status_code)
    )
    """,
    "CREATE INDEX fact_attendance_branch_idx ON dwh.fact_attendance (branch_id, att_date DESC)",
    "ALTER TABLE dwh.fact_attendance ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE dwh.fact_attendance FORCE ROW LEVEL SECURITY",
    "CREATE POLICY branch_scope ON dwh.fact_attendance USING (core.rls_branch_ok(branch_id)) "
    "WITH CHECK (core.rls_branch_ok(branch_id))",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON dwh.fact_attendance TO ugk_etl",
    "GRANT SELECT ON dwh.fact_attendance TO ugk_app",
    """
    CREATE VIEW pub.attendance_daily WITH (security_invoker = true) AS
    SELECT a.att_date, a.branch_id, a.status_code, a.status_label, a.status_kind, a.employees,
           a.person_days, a.branch_employees, a.generated_at
    FROM dwh.fact_attendance a
    """,
    "GRANT SELECT ON pub.attendance_daily TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP VIEW pub.attendance_daily")
    op.execute("DROP TABLE dwh.fact_attendance")
