"""sxemalar, sxema huquqlari, RLS funksiyasi

Revision ID: 0001
Revises:
Create Date: 2026-09-24
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = ("core", "stg", "dwh", "mart", "pub")


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA {schema}")
    op.execute("GRANT USAGE ON SCHEMA core TO ugk_app, ugk_etl")
    op.execute("GRANT USAGE ON SCHEMA pub TO ugk_app")
    op.execute("GRANT USAGE ON SCHEMA stg, dwh, mart TO ugk_etl")
    # RLS: filial doirasi tranzaksiya sozlamalaridan olinadi (app.core.db.apply_rls).
    # branch_id = 0 — "barcha filiallar jami" qatori, faqat scope_all uchun.
    op.execute(
        """
        CREATE FUNCTION core.rls_branch_ok(branch integer) RETURNS boolean
        LANGUAGE sql STABLE PARALLEL SAFE AS $$
          SELECT coalesce(current_setting('app.scope_all', true), '') = 'on'
              OR (branch <> 0 AND branch = ANY (
                    coalesce(nullif(current_setting('app.branch_ids', true), ''), '{}')::int[]))
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION core.rls_branch_ok(integer) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION core.rls_branch_ok(integer) TO ugk_app, ugk_etl")


def downgrade() -> None:
    op.execute("DROP FUNCTION core.rls_branch_ok(integer)")
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA {schema}")
