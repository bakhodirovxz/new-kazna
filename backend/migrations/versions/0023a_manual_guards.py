"""Qo'lda kiritish: DB darajasidagi qo'shimcha himoyalar (security review I1, M9)

Revision ID: 0023a
Revises: 0023
Create Date: 2026-10-27

- `manual_head.approved_version/approved_deleted` faqat tasdiqlangan (status='approved',
  decided_by <> created_by) paketdagi versiyaga ishora qila oladi (ugk_app to'g'ridan-to'g'ri
  SQL bilan draft'ni "tasdiqlangan" qila olmaydi).
- `manual_entry` faqat `draft` paketga va paket yaratuvchisi nomidan qo'shiladi.
- Yakuniy holatdagi (approved/rejected/withdrawn) paket qatori muzlatiladi
  (faqat `etl_request_id` NULL bo'lganda bir marta o'rnatiladi).
"""

from alembic import op

revision = "0023a"
down_revision = "0023"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE FUNCTION core.manual_head_guard() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
    BEGIN
      IF NEW.approved_version IS NOT DISTINCT FROM OLD.approved_version
         AND NEW.approved_deleted IS NOT DISTINCT FROM OLD.approved_deleted THEN
        RETURN NEW;
      END IF;
      IF NEW.approved_version IS NULL THEN
        RAISE EXCEPTION 'manual_head: approved_version cannot be cleared'
          USING ERRCODE = 'check_violation';
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM core.manual_entry e
        JOIN core.manual_batch b ON b.batch_id = e.batch_id
        WHERE e.entry_id = NEW.entry_id AND e.version = NEW.approved_version
          AND e.deleted = NEW.approved_deleted
          AND b.status = 'approved' AND b.decided_by IS NOT NULL
          AND b.decided_by <> b.created_by) THEN
        RAISE EXCEPTION 'manual_head: version is not in an approved batch'
          USING ERRCODE = 'check_violation';
      END IF;
      RETURN NEW;
    END
    $$
    """,
    "CREATE TRIGGER manual_head_guard BEFORE UPDATE ON core.manual_head "
    "FOR EACH ROW EXECUTE FUNCTION core.manual_head_guard()",
    """
    CREATE FUNCTION core.manual_entry_insert_guard() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM core.manual_batch b
                     WHERE b.batch_id = NEW.batch_id AND b.status = 'draft'
                       AND b.created_by = NEW.created_by) THEN
        RAISE EXCEPTION 'manual_entry: only the creator can add to a draft batch'
          USING ERRCODE = 'check_violation';
      END IF;
      RETURN NEW;
    END
    $$
    """,
    "CREATE TRIGGER manual_entry_insert_guard BEFORE INSERT ON core.manual_entry "
    "FOR EACH ROW EXECUTE FUNCTION core.manual_entry_insert_guard()",
    # M9: yakuniy holatdan keyin hech narsa o'zgarmaydi (etl_request_id -- bir marta)
    """
    CREATE OR REPLACE FUNCTION core.manual_batch_guard() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
      mutable text[] := '{status,rows,reason,submitted_at,decided_by,decided_at,decision_comment,content_hash,version,etl_request_id}';
    BEGIN
      IF to_jsonb(OLD) - mutable <> to_jsonb(NEW) - mutable THEN
        RAISE EXCEPTION 'manual_batch: immutable column changed' USING ERRCODE = 'check_violation';
      END IF;
      IF OLD.status IN ('approved', 'rejected', 'withdrawn') THEN
        IF to_jsonb(OLD) - 'etl_request_id' = to_jsonb(NEW) - 'etl_request_id'
           AND (OLD.etl_request_id IS NULL OR NEW.etl_request_id IS NOT DISTINCT FROM OLD.etl_request_id)
        THEN
          RETURN NEW;
        END IF;
        RAISE EXCEPTION 'manual_batch: terminal batch is frozen' USING ERRCODE = 'check_violation';
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
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER manual_entry_insert_guard ON core.manual_entry")
    op.execute("DROP FUNCTION core.manual_entry_insert_guard()")
    op.execute("DROP TRIGGER manual_head_guard ON core.manual_head")
    op.execute("DROP FUNCTION core.manual_head_guard()")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION core.manual_batch_guard() RETURNS trigger
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
        """
    )
