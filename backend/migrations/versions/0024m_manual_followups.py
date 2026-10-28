"""Qo'lda kiritish: hisob <-> filial aloqasi (qoldiq faktlari) va nashr xatosi holati

Revision ID: 0024m
Revises: 0023a
Create Date: 2026-10-28

- `ugk_app` tanlov ro'yxati va tekshiruv uchun `dwh.fact_balance` dan faqat (branch_id, bank_id)
  ni o'qiydi (FORCE RLS filial doirasini baribir cheklaydi; summa/sana/manba ko'rinmaydi).
- Nashr xatosi: tasdiqlangan paket sifat tekshiruvidan o'tmasa ETL roli (`ugk_etl`) uni `failed`
  qiladi va boshlarni oxirgi tasdiqlangan versiyaga qaytaradi. Boshqa hech kim `failed` qila
  olmaydi; `approved_version` NULL ga faqat tasdiqlangan versiya qolmaganda qaytadi.
"""

from alembic import op

revision = "0024m"
down_revision = "0023a"
branch_labels = None
depends_on = None

_MUTABLE = (
    "status,rows,reason,submitted_at,decided_by,decided_at,decision_comment,"
    "content_hash,version,etl_request_id"
)

_FAIL_BLOCK = """  IF OLD.status = 'approved' AND NEW.status = 'failed' THEN
    IF current_user <> 'ugk_etl' THEN
      RAISE EXCEPTION 'manual_batch: only the ETL role can fail a publication'
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
"""

_BATCH_GUARD = """
CREATE OR REPLACE FUNCTION core.manual_batch_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  mutable text[] := '{@MUTABLE@}';
BEGIN
  IF to_jsonb(OLD) - mutable <> to_jsonb(NEW) - mutable THEN
    RAISE EXCEPTION 'manual_batch: immutable column changed' USING ERRCODE = 'check_violation';
  END IF;
@FAIL@  IF OLD.status IN ('approved', 'rejected', 'withdrawn'@TERMINAL@) THEN
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
"""

_CLEAR_NEW = """    IF NEW.approved_deleted OR EXISTS (
        SELECT 1 FROM core.manual_entry e JOIN core.manual_batch b ON b.batch_id = e.batch_id
        WHERE e.entry_id = NEW.entry_id AND b.status = 'approved') THEN
      RAISE EXCEPTION 'manual_head: approved_version cannot be cleared'
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
"""
_CLEAR_OLD = """    RAISE EXCEPTION 'manual_head: approved_version cannot be cleared'
      USING ERRCODE = 'check_violation';
"""

_HEAD_GUARD = """
CREATE OR REPLACE FUNCTION core.manual_head_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF NEW.approved_version IS NOT DISTINCT FROM OLD.approved_version
     AND NEW.approved_deleted IS NOT DISTINCT FROM OLD.approved_deleted THEN
    RETURN NEW;
  END IF;
  IF NEW.approved_version IS NULL THEN
@CLEAR@  END IF;
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
"""


def _batch_guard(new: bool) -> str:
    return (
        _BATCH_GUARD.replace("@MUTABLE@", _MUTABLE + (",publish_error" if new else ""))
        .replace("@FAIL@", _FAIL_BLOCK if new else "")
        .replace("@TERMINAL@", ", 'failed'" if new else "")
    )


def _head_guard(new: bool) -> str:
    return _HEAD_GUARD.replace("@CLEAR@", _CLEAR_NEW if new else _CLEAR_OLD)


STATEMENTS = [
    "GRANT SELECT (branch_id, bank_id) ON dwh.fact_balance TO ugk_app",
    "ALTER TABLE core.manual_batch DROP CONSTRAINT manual_batch_status_check",
    "ALTER TABLE core.manual_batch ADD CONSTRAINT manual_batch_status_check CHECK "
    "(status IN ('draft', 'submitted', 'approved', 'rejected', 'withdrawn', 'failed'))",
    "ALTER TABLE core.manual_batch ADD COLUMN publish_error varchar(300)",
    _batch_guard(True),
    _head_guard(True),
    "GRANT UPDATE (status, publish_error, version) ON core.manual_batch TO ugk_etl",
    "GRANT UPDATE (approved_version, approved_deleted, updated_at) ON core.manual_head TO ugk_etl",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("REVOKE UPDATE (approved_version, approved_deleted, updated_at) "
               "ON core.manual_head FROM ugk_etl")
    op.execute("REVOKE UPDATE (status, publish_error, version) ON core.manual_batch FROM ugk_etl")
    op.execute(_head_guard(False))
    op.execute(_batch_guard(False))
    op.execute("ALTER TABLE core.manual_batch DROP COLUMN publish_error")
    op.execute("ALTER TABLE core.manual_batch DROP CONSTRAINT manual_batch_status_check")
    op.execute("ALTER TABLE core.manual_batch ADD CONSTRAINT manual_batch_status_check CHECK "
               "(status IN ('draft', 'submitted', 'approved', 'rejected', 'withdrawn'))")
    op.execute("REVOKE SELECT (branch_id, bank_id) ON dwh.fact_balance FROM ugk_app")
