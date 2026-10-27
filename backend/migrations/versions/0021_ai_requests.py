"""S5: AI-анализ jurnali va limitlar hisobi (core.ai_requests), 90 kun saqlanadi

Revision ID: 0021
Revises: 0010
Create Date: 2026-10-27

Jurnal = limit reyestri: so'rov qabul qilinganda `running` yozuv (advisory lock ostida), oqim
tugaganda holat. ugk_app o'chira olmaydi — tozalash faqat worker (ugk_etl) orqali.
Eslatma: reja 0020 ga zanjirlagan; bu shoxda 0020 yo'q — integrator qayta zanjirlaydi.
"""

from alembic import op

revision = "0021"
down_revision = "0010"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE core.ai_requests (
      id bigserial PRIMARY KEY,
      created_at timestamptz NOT NULL DEFAULT now(),
      finished_at timestamptz,
      user_id bigint NOT NULL REFERENCES core.users (id),
      section varchar(32) NOT NULL,
      page varchar(32) NOT NULL,
      filters jsonb NOT NULL DEFAULT '{}'::jsonb,
      preset varchar(16),
      question varchar(500),
      status varchar(12) NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'ok', 'error', 'timeout', 'cancelled', 'refused')),
      error_code varchar(32),
      context_chars integer NOT NULL CHECK (context_chars >= 0),
      answer_chars integer NOT NULL DEFAULT 0 CHECK (answer_chars >= 0),
      provider varchar(32) NOT NULL,
      model varchar(64) NOT NULL,
      duration_ms integer
    )
    """,
    "CREATE INDEX ai_requests_user_created_idx ON core.ai_requests (user_id, created_at)",
    "CREATE INDEX ai_requests_created_idx ON core.ai_requests (created_at)",
    "GRANT SELECT, INSERT, UPDATE ON core.ai_requests TO ugk_app",
    "GRANT USAGE ON SEQUENCE core.ai_requests_id_seq TO ugk_app",
    "GRANT SELECT, UPDATE, DELETE ON core.ai_requests TO ugk_etl",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE core.ai_requests")
