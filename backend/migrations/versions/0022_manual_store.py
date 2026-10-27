"""Qo'lda kiritish ombori: paket / bosh / versiya, RLS FORCE, append-only va SoD triggerlari

Revision ID: 0022
Revises: 0010
Create Date: 2026-10-27

`dwh`/`mart` ga bu yerdan HECH narsa yozilmaydi: tasdiqlangan yozuvlarni ManualConnector
o'qiydi (ugk_etl: faqat SELECT) va Runner orqali yuklaydi. `ugk_app` ga o'lchovlardan faqat
sezgir bo'lmagan ustunlar uchun SELECT beriladi (tanlov ro'yxatlari).
"""

from alembic import op

revision = "0022"
down_revision = "0010"  # integrator qayta zanjirlaydi
branch_labels = None
depends_on = None

TABLES = ("manual_batch", "manual_head", "manual_entry")

STATEMENTS = [
    """
    CREATE TABLE core.manual_batch (
      batch_id bigserial PRIMARY KEY,
      entity varchar(48) NOT NULL,
      branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id),
      status varchar(10) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'approved', 'rejected', 'withdrawn')),
      origin varchar(8) NOT NULL CHECK (origin IN ('form', 'grid', 'import')),
      file_name varchar(200),
      file_sha256 bytea,
      rows integer NOT NULL DEFAULT 0,
      reason varchar(500),
      created_by bigint NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      submitted_at timestamptz,
      decided_by bigint,
      decided_at timestamptz,
      decision_comment varchar(500),
      content_hash bytea,
      version integer NOT NULL DEFAULT 1,
      etl_request_id bigint,
      -- Vazifalar ajratilishi: o'zini tasdiqlash/rad etish DB darajasida ham yopiq.
      CONSTRAINT manual_batch_sod CHECK (decided_by IS NULL OR decided_by <> created_by),
      CONSTRAINT manual_batch_decided CHECK (
        status NOT IN ('approved', 'rejected')
        OR (decided_by IS NOT NULL AND decided_at IS NOT NULL))
    )
    """,
    "CREATE INDEX manual_batch_submitted_idx ON core.manual_batch (status, batch_id) "
    "WHERE status = 'submitted'",
    "CREATE INDEX manual_batch_creator_idx ON core.manual_batch (created_by, batch_id DESC)",
    """
    CREATE TABLE core.manual_head (
      entry_id bigserial PRIMARY KEY,
      entity varchar(48) NOT NULL,
      branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id),
      business_key varchar(200) NOT NULL,
      code varchar(32),
      approved_version integer,
      approved_deleted boolean NOT NULL DEFAULT false,
      pending_batch_id bigint REFERENCES core.manual_batch (batch_id),
      version integer NOT NULL DEFAULT 0,
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (entity, business_key)
    )
    """,
    "CREATE UNIQUE INDEX manual_head_code_uq ON core.manual_head (code) WHERE code IS NOT NULL",
    "CREATE INDEX manual_head_pending_idx ON core.manual_head (pending_batch_id) "
    "WHERE pending_batch_id IS NOT NULL",
    """
    CREATE TABLE core.manual_entry (
      id bigserial PRIMARY KEY,
      entry_id bigint NOT NULL REFERENCES core.manual_head (entry_id),
      version integer NOT NULL CHECK (version > 0),
      batch_id bigint NOT NULL REFERENCES core.manual_batch (batch_id),
      branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id),
      payload jsonb NOT NULL,
      bank_enc bytea,
      pii_enc bytea,
      masks jsonb NOT NULL DEFAULT '{}',
      deleted boolean NOT NULL DEFAULT false,
      created_by bigint NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (entry_id, version)
    )
    """,
    "CREATE INDEX manual_entry_batch_idx ON core.manual_entry (batch_id)",
    # --- Filial doirasi: FORCE RLS, WITH CHECK ---
    *[
        stmt
        for t in TABLES
        for stmt in (
            f"ALTER TABLE core.{t} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE core.{t} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY branch_scope ON core.{t} USING (core.rls_branch_ok(branch_id)) "
            "WITH CHECK (core.rls_branch_ok(branch_id))",
        )
    ],
    # --- Versiya: append-only (faqat *_enc qayta shifrlash), DELETE faqat draft paketda ---
    """
    CREATE FUNCTION core.manual_entry_guard() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
    BEGIN
      IF TG_OP = 'UPDATE' THEN
        IF to_jsonb(OLD) - '{bank_enc,pii_enc}'::text[]
           = to_jsonb(NEW) - '{bank_enc,pii_enc}'::text[] THEN
          RETURN NEW;
        END IF;
        RAISE EXCEPTION 'manual_entry is append-only' USING ERRCODE = 'check_violation';
      END IF;
      IF EXISTS (SELECT 1 FROM core.manual_batch b
                 WHERE b.batch_id = OLD.batch_id AND b.status = 'draft') THEN
        RETURN OLD;
      END IF;
      RAISE EXCEPTION 'manual_entry rows of a non-draft batch cannot be deleted'
        USING ERRCODE = 'check_violation';
    END
    $$
    """,
    "CREATE TRIGGER manual_entry_guard BEFORE UPDATE OR DELETE ON core.manual_entry "
    "FOR EACH ROW EXECUTE FUNCTION core.manual_entry_guard()",
    # --- Paket: faqat ruxsat etilgan holat o'tishlari ---
    """
    CREATE FUNCTION core.manual_batch_guard() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
      mutable text[] := '{status,rows,reason,submitted_at,decided_by,decided_at,decision_comment,content_hash,version,etl_request_id}';
    BEGIN
      IF to_jsonb(OLD) - mutable <> to_jsonb(NEW) - mutable THEN
        RAISE EXCEPTION 'manual_batch: immutable column changed' USING ERRCODE = 'check_violation';
      END IF;
      IF NEW.status = OLD.status OR (OLD.status, NEW.status) IN (
           ('draft', 'submitted'), ('draft', 'withdrawn'),
           ('submitted', 'approved'), ('submitted', 'rejected'), ('submitted', 'withdrawn')) THEN
        RETURN NEW;
      END IF;
      RAISE EXCEPTION 'manual_batch: illegal transition % -> %', OLD.status, NEW.status
        USING ERRCODE = 'check_violation';
    END
    $$
    """,
    "CREATE TRIGGER manual_batch_guard BEFORE UPDATE ON core.manual_batch "
    "FOR EACH ROW EXECUTE FUNCTION core.manual_batch_guard()",
    # --- Grantlar: ugk_app yozadi (ustun darajasida), ugk_etl faqat o'qiydi ---
    "GRANT SELECT, INSERT ON core.manual_batch, core.manual_head, core.manual_entry TO ugk_app",
    "GRANT UPDATE (status, rows, reason, submitted_at, decided_by, decided_at, decision_comment, "
    "content_hash, version, etl_request_id) ON core.manual_batch TO ugk_app",
    "GRANT UPDATE (approved_version, approved_deleted, pending_batch_id, version, updated_at, "
    "code) ON core.manual_head TO ugk_app",
    "GRANT UPDATE (bank_enc, pii_enc) ON core.manual_entry TO ugk_app",
    "GRANT DELETE ON core.manual_entry TO ugk_app",
    "GRANT USAGE ON SEQUENCE core.manual_batch_batch_id_seq, core.manual_head_entry_id_seq, "
    "core.manual_entry_id_seq TO ugk_app",
    "GRANT SELECT ON core.manual_batch, core.manual_head, core.manual_entry TO ugk_etl",
    # Tanlov ro'yxati (bank hisoblari): faqat sezgir bo'lmagan ustunlar; account_enc/bidx YO'Q.
    "ALTER TABLE dwh.dim_bank ADD COLUMN account_last4 varchar(4) "
    "CHECK (account_last4 ~ '^[0-9]{4}$')",
    "GRANT SELECT (bank_id, code, bank_name, currency, account_last4) ON dwh.dim_bank TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT (bank_id, code, bank_name, currency, account_last4) "
        "ON dwh.dim_bank FROM ugk_app"
    )
    op.execute("ALTER TABLE dwh.dim_bank DROP COLUMN account_last4")
    for table in ("manual_entry", "manual_head", "manual_batch"):
        op.execute(f"DROP TABLE core.{table}")
    op.execute("DROP FUNCTION core.manual_batch_guard()")
    op.execute("DROP FUNCTION core.manual_entry_guard()")
