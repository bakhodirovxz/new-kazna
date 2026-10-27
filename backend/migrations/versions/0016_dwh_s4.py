"""S4: obyekt bosqichlari fakti (fact_object_stage) va fact_procurement holat/usul cheklovlari

Revision ID: 0016
Revises: 0010
Create Date: 2026-09-25

Holat va usul qiymatlari app/etl/zakupki/codes.py bilan bir xil (test tekshiradi); migratsiya
ilova kodini import qilmaydi.
"""

from alembic import op

revision = "0016"
down_revision = "0010"  # S4 shoxida: integrator qayta zanjirlaydi
branch_labels = None
depends_on = None

STATUSES = "'объявлен', 'на оценке', 'договор заключён', 'отменён', 'план'"
METHODS = "'eshop', 'contest', 'tender', 'exchange', 'direct', 'other', 'plan'"
FK = "DEFERRABLE INITIALLY DEFERRED"

STAGE_TABLE = f"""
CREATE TABLE dwh.fact_object_stage (
  date_id integer NOT NULL REFERENCES dwh.dim_date (date_id) {FK},
  branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id) {FK},
  object_id integer NOT NULL REFERENCES dwh.dim_object (object_id) {FK},
  stage_no smallint NOT NULL CHECK (stage_no BETWEEN 1 AND 30),
  stage_name varchar(200) NOT NULL,
  fact_date_id integer,
  load_id bigint NOT NULL,
  src_system varchar(32) NOT NULL,
  doc_type varchar(32) NOT NULL,
  src_id varchar(128) NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fact_object_stage_src_uq UNIQUE (src_system, doc_type, src_id)
)
"""


def upgrade() -> None:
    op.execute(STAGE_TABLE)
    op.execute("CREATE INDEX fact_object_stage_date_id_branch_id_idx "
               "ON dwh.fact_object_stage (date_id, branch_id)")
    op.execute("CREATE INDEX fact_object_stage_branch_id_idx ON dwh.fact_object_stage (branch_id)")
    op.execute("CREATE INDEX fact_object_stage_object_id_idx ON dwh.fact_object_stage (object_id)")
    op.execute("ALTER TABLE dwh.fact_object_stage ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dwh.fact_object_stage FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY branch_scope ON dwh.fact_object_stage "
               "USING (core.rls_branch_ok(branch_id)) WITH CHECK (core.rls_branch_ok(branch_id))")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON dwh.fact_object_stage TO ugk_etl")
    op.execute(f"ALTER TABLE dwh.fact_procurement ADD CONSTRAINT fact_procurement_status_ck "
               f"CHECK (status IN ({STATUSES}))")
    op.execute(f"ALTER TABLE dwh.fact_procurement ADD CONSTRAINT fact_procurement_method_ck "
               f"CHECK (method IN ({METHODS}))")
    op.execute("ALTER TABLE dwh.fact_procurement ADD CONSTRAINT fact_procurement_amounts_ck "
               "CHECK (start_price >= 0 AND (contract_price IS NULL OR contract_price >= 0) "
               "AND (procedure_days IS NULL OR procedure_days >= 0))")


def downgrade() -> None:
    for name in ("amounts", "method", "status"):
        op.execute(f"ALTER TABLE dwh.fact_procurement DROP CONSTRAINT fact_procurement_{name}_ck")
    op.execute("DROP TABLE dwh.fact_object_stage")
