"""S2: bank fayllari jurnali, ko'chirma ↔ 1C ustuvorligi view'lari, oxirgi kurslar view'i

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-25
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE core.bank_files (
      sha256 char(64) PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
      bank_code varchar(16) NOT NULL,
      file_name varchar(255) NOT NULL,
      size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
      kind varchar(16) NOT NULL CHECK (kind IN ('statement', 'orders', 'unknown')),
      status varchar(16) NOT NULL CHECK (status IN ('staged', 'rejected')),
      run_id bigint REFERENCES core.etl_run (id) ON DELETE SET NULL,
      row_count integer NOT NULL DEFAULT 0,
      error_count integer NOT NULL DEFAULT 0,
      archive_path varchar(300),
      first_seen_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX bank_files_run_idx ON core.bank_files (run_id)",
    "GRANT SELECT, INSERT, UPDATE ON core.bank_files TO ugk_etl",
    "GRANT SELECT ON core.bank_files TO ugk_app",
    # S2 spec 3.4: oqimi bank ko'chirmasidan olinadigan filiallar (sozlama banks.statement_branches).
    """
    CREATE VIEW dwh.statement_branches WITH (security_invoker = true) AS
    SELECT b.branch_id FROM dwh.dim_branch b
    WHERE b.code IN (SELECT jsonb_array_elements_text(s.value) FROM core.settings s
                     WHERE s.key = 'banks.statement_branches' AND s.is_current)
    """,
    # Ko'chirma filialida — faqat bank проводкалари, qolganlarida — 1C; boshqa manbalar doim.
    """
    CREATE VIEW dwh.cashflow_effective WITH (security_invoker = true) AS
    SELECT f.* FROM dwh.fact_cashflow f
    WHERE CASE
      WHEN f.doc_type = 'bank_statement'
        THEN f.branch_id IN (SELECT sb.branch_id FROM dwh.statement_branches sb)
      WHEN left(f.doc_type, 5) = 'onec_'
        THEN f.branch_id NOT IN (SELECT sb.branch_id FROM dwh.statement_branches sb)
      ELSE true END
    """,
    "GRANT SELECT ON dwh.statement_branches, dwh.cashflow_effective TO ugk_etl",
    # Kurslar maxfiy emas va filialga bog'liq emas; ugk_app dwh.fx_rate'ga bevosita kira olmaydi
    # (test_ugk_app_denied_select_on_fx_rate), shuning uchun view egasi (migrator) huquqida ishlaydi.
    """
    CREATE VIEW pub.fx_rate_latest AS
    SELECT DISTINCT ON (r.currency) r.currency, r.date_id, r.rate
    FROM dwh.fx_rate r ORDER BY r.currency, r.date_id DESC
    """,
    "GRANT SELECT ON pub.fx_rate_latest TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP VIEW pub.fx_rate_latest")
    op.execute("DROP VIEW dwh.cashflow_effective")
    op.execute("DROP VIEW dwh.statement_branches")
    op.execute("DROP TABLE core.bank_files")
