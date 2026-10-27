"""integratsiya hisob ma'lumotlari va ulanish tekshiruvlari (04b-reja)

Revision ID: 0008a
Revises: 0008
Create Date: 2026-10-26
"""

from alembic import op

revision = "0008a"
down_revision = "0008"
branch_labels = None
depends_on = None

STATEMENTS = [
    # Tarix saqlanmaydi: eski sir qatori qolmaydi; o'zgarish — audit (set/cleared).
    # value_enc ≥ 32 bayt: 15 bayt sarlavha+nonce + ≥ 1 bayt + 16 bayt tag (app/core/crypto.py).
    r"""
    CREATE TABLE core.integration_credentials (
      name varchar(64) PRIMARY KEY CHECK (name ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'),
      value_enc bytea NOT NULL CHECK (octet_length(value_enc) >= 32),
      updated_by bigint,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE core.integration_checks (
      id bigserial PRIMARY KEY,
      name varchar(32) NOT NULL,
      requested_by bigint NOT NULL,
      requested_at timestamptz NOT NULL DEFAULT now(),
      status varchar(8) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'ok', 'failed')),
      code varchar(32),
      finished_at timestamptz
    )
    """,
    "CREATE INDEX integration_checks_open_idx ON core.integration_checks (name, id) "
    "WHERE status IN ('pending', 'running')",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON core.integration_credentials TO ugk_app",
    "GRANT SELECT ON core.integration_credentials TO ugk_etl",
    "GRANT SELECT, INSERT, UPDATE ON core.integration_checks TO ugk_app",
    "GRANT USAGE ON SEQUENCE core.integration_checks_id_seq TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE core.integration_checks")
    op.execute("DROP TABLE core.integration_credentials")
