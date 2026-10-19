"""mart oylik agregatlari va pub view'lari (faqat aktiv build)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-24
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_cash_month (
      build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE,
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      item_id integer NOT NULL CHECK (item_id >= 0),
      inflow {MONEY},
      outflow {MONEY},
      inflow_cmp {MONEY},
      outflow_cmp {MONEY},
      days_in_period smallint NOT NULL,
      opening_balance numeric(20,2),
      closing_balance numeric(20,2),
      diff numeric(20,2),
      PRIMARY KEY (build_id, branch_id, month_id, item_id)
    )
    """,
    f"""
    CREATE TABLE mart.agg_payments_month (
      build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE,
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      item_id integer NOT NULL CHECK (item_id >= 0),
      plan_amount {MONEY},
      fact_amount {MONEY},
      fact_cmp {MONEY},
      days_in_period smallint NOT NULL,
      PRIMARY KEY (build_id, branch_id, month_id, item_id)
    )
    """,
    f"""
    CREATE VIEW pub.agg_cash_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.item_id, a.inflow, a.outflow, a.inflow_cmp, a.outflow_cmp,
           a.days_in_period, a.opening_balance, a.closing_balance, a.diff
    FROM mart.agg_cash_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_payments_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.item_id, a.plan_amount, a.fact_amount, a.fact_cmp,
           a.days_in_period
    FROM mart.agg_payments_month a WHERE a.build_id = {ACTIVE}
    """,
    """
    CREATE VIEW pub.branches WITH (security_invoker = true) AS
    SELECT branch_id, code, name, short_name, kind, capacity_mw, lat, lon, sort_order
    FROM dwh.dim_branch
    """,
    """
    CREATE VIEW pub.items WITH (security_invoker = true) AS
    SELECT item_id, code, name, activity, direction, sort_order FROM dwh.dim_item
    """,
    "GRANT USAGE ON SCHEMA mart TO ugk_app",
    "GRANT SELECT ON mart.agg_cash_month, mart.agg_payments_month TO ugk_app",
    "GRANT SELECT, INSERT, DELETE ON mart.agg_cash_month, mart.agg_payments_month TO ugk_etl",
    "GRANT SELECT ON pub.agg_cash_month, pub.agg_payments_month, pub.branches, pub.items TO ugk_app",
]

# Fix r1 (M1): DB darajasidagi himoya — `core.data_version.active_build_id` faqat
# "nashr qilinishi mumkin" holatdagi build'ga ko'rsatishi mumkin. `app/dwh/builds.py`ning
# `publish()`/`rollback()` funksiyalari buni allaqachon Python darajasida tekshiradi, lekin
# 0007'da `ugk_app`ga `data_version.active_build_id` ustuniga to'g'ridan-to'g'ri UPDATE
# huquqi berilgani sababli (kelajakdagi admin rollback so'rovi uchun), trigger — ikkinchi
# himoya qatlami: ilova kodini chetlab o'tib to'g'ridan-to'g'ri UPDATE qilingan taqdirda ham
# `failed`/`building` build faol qilinmasin. SECURITY INVOKER (DEFINER emas) — imtiyozni
# oshirmaydi, shuning uchun Plan 2'ning SECURITY DEFINER konvensiyasi bu yerga tegishli emas;
# baribir `search_path` mudofaa chuqurligi uchun qotirilgan.
TRIGGER_FUNCTION = """
CREATE FUNCTION core.data_version_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  st text;
BEGIN
  IF NEW.active_build_id IS NOT NULL THEN
    SELECT status INTO st FROM core.builds WHERE build_id = NEW.active_build_id;
    -- Final review (I1): 'ready' (hali nashr qilinmagan) faqat ugk_etl uchun.
    IF st IS NULL OR NOT (st IN ('published', 'superseded')
                          OR (st = 'ready' AND current_user = 'ugk_etl')) THEN
      RAISE EXCEPTION 'core.data_version.active_build_id: build % is not publishable (status %)',
        NEW.active_build_id, st;
    END IF;
  END IF;
  RETURN NEW;
END
$$
"""
TRIGGER = """
CREATE TRIGGER data_version_guard BEFORE UPDATE ON core.data_version
FOR EACH ROW EXECUTE FUNCTION core.data_version_guard()
"""


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for table in ("agg_cash_month", "agg_payments_month"):
        op.execute(f"ALTER TABLE mart.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE mart.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY branch_scope ON mart.{table} USING (core.rls_branch_ok(branch_id)) "
            "WITH CHECK (core.rls_branch_ok(branch_id))"
        )
    op.execute(TRIGGER_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION core.data_version_guard() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION core.data_version_guard() TO ugk_app, ugk_etl")
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER data_version_guard ON core.data_version")
    op.execute("DROP FUNCTION core.data_version_guard()")
    for view in ("items", "branches", "agg_payments_month", "agg_cash_month"):
        op.execute(f"DROP VIEW pub.{view}")
    op.execute("DROP TABLE mart.agg_payments_month")
    op.execute("DROP TABLE mart.agg_cash_month")
    # Fix r1 (M10): 0007/upgrade()dagi simmetriyasiz qoldirilgan — jadvallar tushirilsa ham
    # sxema darajasidagi USAGE granti alohida yashaydi (mart sxemasi o'zi bu yerda
    # tushirilmaydi, u 0001'da yaratilgan).
    op.execute("REVOKE USAGE ON SCHEMA mart FROM ugk_app")
