"""shifrlash kalitlari (DEK, KEK bilan o'ralgan)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-24
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE core.crypto_keys (
          id bigserial PRIMARY KEY,
          purpose text NOT NULL
            CHECK (purpose IN ('pii', 'bank', 'mfa', 'integration_creds', 'audit_meta',
                               'audit_chain')),
          version integer NOT NULL CHECK (version > 0 AND version <= 65535),
          wrapped_key bytea NOT NULL,
          status text NOT NULL CHECK (status IN ('active', 'decrypt_only', 'retired')),
          created_at timestamptz NOT NULL DEFAULT now(),
          retired_at timestamptz,
          UNIQUE (purpose, version)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX crypto_keys_one_active ON core.crypto_keys (purpose) "
        "WHERE status = 'active'"
    )
    # ugk_app 'wrapped_key' ni qayta yoza olmasin (crypto-shredding'dan himoya, spec 3.5):
    # rotate faqat status/retired_at'ni o'zgartiradi va INSERT qiladi; rewrap_all esa
    # ugk_migrator (jadval egasi) sifatida operator amali sifatida bajariladi.
    op.execute("GRANT SELECT, INSERT ON core.crypto_keys TO ugk_app")
    op.execute("GRANT UPDATE (status, retired_at) ON core.crypto_keys TO ugk_app")
    op.execute("GRANT SELECT ON core.crypto_keys TO ugk_etl")
    op.execute("GRANT USAGE ON SEQUENCE core.crypto_keys_id_seq TO ugk_app")


def downgrade() -> None:
    op.execute("DROP TABLE core.crypto_keys")
