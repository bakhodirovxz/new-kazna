"""ETL jurnali, buildlar, data_version, staging, versiyali sozlamalar

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-24

`ugk_etl`ga `TEMPORARY` huquqi shu yerda ham berilgan (pastga qarang): `app/etl/merge.py` har bir
maqsad uchun qator darajasidagi tekshiruvni bitta o'tishda materiallashtirish uchun
`CREATE TEMP TABLE ... ON COMMIT DROP` ishlatadi (task-5 fix round 2, R2-4). Standart holatda
faqat egasi (`ugk_migrator`) bu huquqqa ega — aks holda `InsufficientPrivilege: permission denied
to create temporary tables` bilan yiqiladi. Vaqtinchalik jadvallar sessiya/tranzaksiya doirasida
(`pg_temp_*` sxema) — boshqa rollarga umuman ko'rinmaydi, shuning uchun bu RLS yoki ma'lumot
izolyatsiyasiga ta'sir qilmaydi. (Bu grant dastlab alohida 0008 migratsiyasida edi — migratsiya
raqami keyingi rejalar uchun band qilinganidan so'ng shu yerga ko'chirildi.)
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE core.builds (
      build_id bigserial PRIMARY KEY,
      created_at timestamptz NOT NULL DEFAULT now(),
      status varchar(16) NOT NULL
        CHECK (status IN ('building', 'ready', 'published', 'superseded', 'failed')),
      load_id bigint,
      published_at timestamptz
    )
    """,
    "CREATE INDEX builds_status_idx ON core.builds (status, build_id DESC)",
    """
    CREATE TABLE core.data_version (
      id smallint PRIMARY KEY CHECK (id = 1),
      active_build_id bigint REFERENCES core.builds (build_id),
      published_at timestamptz
    )
    """,
    # Fix r1 (M1): yagona tizim qatori — migratsiya tomonidan bir marta seed qilinadi
    # (ugk_app'da endi bu jadvalga INSERT huquqi yo'q, faqat ustun darajasidagi UPDATE).
    "INSERT INTO core.data_version (id) VALUES (1)",
    """
    CREATE TABLE core.etl_run (
      id bigserial PRIMARY KEY,
      source varchar(32) NOT NULL,
      mode varchar(16) NOT NULL CHECK (mode IN ('full', 'incremental')),
      started_at timestamptz NOT NULL DEFAULT now(),
      finished_at timestamptz,
      status varchar(16) NOT NULL
        CHECK (status IN ('running', 'success', 'failed', 'failed_quality')),
      window_from date,
      window_to date,
      watermark timestamptz,
      rows_in integer NOT NULL DEFAULT 0,
      rows_upserted integer NOT NULL DEFAULT 0,
      build_id bigint,
      triggered_by bigint,
      error varchar(1000)
    )
    """,
    "CREATE INDEX etl_run_source_idx ON core.etl_run (source, id DESC)",
    "CREATE INDEX etl_run_success_idx ON core.etl_run (finished_at DESC) WHERE status = 'success'",
    """
    CREATE TABLE core.etl_step (
      id bigserial PRIMARY KEY,
      run_id bigint NOT NULL REFERENCES core.etl_run (id) ON DELETE CASCADE,
      name varchar(16) NOT NULL
        CHECK (name IN ('extract', 'dims', 'facts', 'aggregates', 'quality', 'publish')),
      started_at timestamptz NOT NULL DEFAULT now(),
      finished_at timestamptz,
      status varchar(8) NOT NULL CHECK (status IN ('running', 'success', 'failed')),
      rows integer NOT NULL DEFAULT 0,
      detail jsonb NOT NULL DEFAULT '{}'::jsonb
    )
    """,
    "CREATE INDEX etl_step_run_idx ON core.etl_step (run_id, id)",
    """
    CREATE TABLE core.etl_error (
      id bigserial PRIMARY KEY,
      run_id bigint NOT NULL REFERENCES core.etl_run (id) ON DELETE CASCADE,
      step varchar(16) NOT NULL,
      severity varchar(8) NOT NULL CHECK (severity IN ('warning', 'error')),
      target varchar(64),
      src_id varchar(128),
      code varchar(32) NOT NULL,
      message varchar(500) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX etl_error_run_idx ON core.etl_error (run_id, code)",
    """
    CREATE TABLE core.etl_requests (
      id bigserial PRIMARY KEY,
      source varchar(32) NOT NULL,
      mode varchar(16) NOT NULL CHECK (mode IN ('full', 'incremental')),
      requested_by bigint NOT NULL,
      requested_at timestamptz NOT NULL DEFAULT now(),
      status varchar(8) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),
      run_id bigint,
      error varchar(500)
    )
    """,
    "CREATE INDEX etl_requests_pending_idx ON core.etl_requests (id) WHERE status = 'pending'",
    """
    CREATE TABLE core.settings (
      key varchar(64) NOT NULL,
      version integer NOT NULL CHECK (version > 0),
      value jsonb NOT NULL,
      is_current boolean NOT NULL DEFAULT true,
      updated_by bigint,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (key, version)
    )
    """,
    "CREATE UNIQUE INDEX settings_current ON core.settings (key) WHERE is_current",
    """
    CREATE TABLE core.alert_rules (
      code varchar(64) NOT NULL,
      version integer NOT NULL CHECK (version > 0),
      title varchar(200) NOT NULL,
      section varchar(32) NOT NULL,
      page varchar(32) NOT NULL,
      threshold jsonb NOT NULL,
      level varchar(8) NOT NULL CHECK (level IN ('critical', 'warning')),
      enabled boolean NOT NULL DEFAULT true,
      is_current boolean NOT NULL DEFAULT true,
      updated_by bigint,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (code, version)
    )
    """,
    "CREATE UNIQUE INDEX alert_rules_current ON core.alert_rules (code) WHERE is_current",
    """
    CREATE TABLE core.fin_assumptions (
      scenario varchar(8) NOT NULL CHECK (scenario IN ('base', 'water', 'tariff', 'fx')),
      year smallint NOT NULL CHECK (year BETWEEN 2020 AND 2100),
      key varchar(64) NOT NULL,
      version integer NOT NULL CHECK (version > 0),
      value numeric(18,6) NOT NULL,
      is_current boolean NOT NULL DEFAULT true,
      updated_by bigint,
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (scenario, year, key, version)
    )
    """,
    """
    CREATE UNIQUE INDEX fin_assumptions_current ON core.fin_assumptions (scenario, year, key)
    WHERE is_current
    """,
    """
    CREATE TABLE stg.batch (
      load_id bigint NOT NULL,
      target varchar(64) NOT NULL,
      source varchar(32) NOT NULL,
      received_at timestamptz NOT NULL DEFAULT now(),
      row_count integer NOT NULL,
      PRIMARY KEY (load_id, target)
    )
    """,
    # UNLOGGED: staging vaqtinchalik, WAL va replikatsiyaga yuk bermaydi.
    """
    CREATE UNLOGGED TABLE stg.rows (
      seq bigserial PRIMARY KEY,
      load_id bigint NOT NULL,
      target varchar(64) NOT NULL,
      payload jsonb NOT NULL
    )
    """,
    "CREATE INDEX stg_rows_load_idx ON stg.rows (load_id, target)",
    "CREATE INDEX stg_rows_key_idx ON stg.rows (load_id, target, (payload->>'src_id'))",
    # ── Huquqlar ──
    "GRANT SELECT, INSERT, UPDATE, DELETE ON core.builds TO ugk_etl",
    # Fix r1 (M1): ugk_app faqat status/published_at ustunlarini yangilay oladi (masalan,
    # kelajakdagi admin rollback so'rovi uchun) — boshqa ustunlar (build_id, created_at,
    # load_id) faqat ugk_etl orqali yoziladi.
    "GRANT SELECT ON core.builds TO ugk_app",
    "GRANT UPDATE (status, published_at) ON core.builds TO ugk_app",
    "GRANT USAGE ON SEQUENCE core.builds_build_id_seq TO ugk_etl",
    # Final review (I1): ugk_app faqat published<->superseded o'tishlarini qila oladi (API
    # rollback); building/ready/failed holatlarini faqat ugk_etl o'zgartiradi. Aks holda
    # ugk_app failed build'ni 'superseded'ga aylantirib, uni faol qila olardi.
    """
    CREATE FUNCTION core.builds_guard() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
    BEGIN
      IF current_user = 'ugk_etl' THEN
        RETURN NEW;
      END IF;
      IF OLD.status IN ('published', 'superseded') AND NEW.status IN ('published', 'superseded')
         AND (NEW.status = 'published' OR NEW.published_at IS NOT DISTINCT FROM OLD.published_at)
      THEN
        RETURN NEW;
      END IF;
      RAISE EXCEPTION 'core.builds: status % -> % is allowed only for ugk_etl',
        OLD.status, NEW.status USING ERRCODE = 'check_violation';
    END
    $$
    """,
    "CREATE TRIGGER builds_guard BEFORE UPDATE ON core.builds "
    "FOR EACH ROW EXECUTE FUNCTION core.builds_guard()",
    "GRANT SELECT, UPDATE ON core.data_version TO ugk_etl",
    # Fix r1 (M1): INSERT yo'q — yagona qator migratsiya tomonidan seed qilingan (yuqorida).
    # UPDATE faqat active_build_id/published_at ustunlariga — 0008'dagi BEFORE UPDATE
    # trigger (core.data_version_guard) active_build_id noto'g'ri build'ga ko'rsatishidan
    # DB darajasida himoya qiladi (ugk_app to'g'ridan-to'g'ri UPDATE qilsa ham).
    "GRANT SELECT ON core.data_version TO ugk_app",
    "GRANT UPDATE (active_build_id, published_at) ON core.data_version TO ugk_app",
    "GRANT SELECT, INSERT, UPDATE ON core.etl_run, core.etl_step, core.etl_error TO ugk_etl",
    "GRANT SELECT ON core.etl_run, core.etl_step, core.etl_error TO ugk_app",
    """
    GRANT USAGE ON SEQUENCE core.etl_run_id_seq, core.etl_step_id_seq, core.etl_error_id_seq
    TO ugk_etl
    """,
    "GRANT SELECT, INSERT ON core.etl_requests TO ugk_app",
    "GRANT SELECT, UPDATE ON core.etl_requests TO ugk_etl",
    "GRANT USAGE ON SEQUENCE core.etl_requests_id_seq TO ugk_app",
    # Versiyali jadvallar: faqat INSERT + eski qatorni arxivlash (is_current) — qiymatlar
    # joyida o'zgarmaydi; trigger ikkinchi himoya qatlami (pastda).
    "GRANT SELECT, INSERT ON core.settings, core.alert_rules, core.fin_assumptions TO ugk_app",
    "GRANT UPDATE (is_current) ON core.settings, core.alert_rules, core.fin_assumptions "
    "TO ugk_app",
    "GRANT SELECT ON core.settings, core.alert_rules, core.fin_assumptions TO ugk_etl",
    """
    CREATE FUNCTION core.versioned_guard() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
    BEGIN
      IF OLD.is_current AND NOT NEW.is_current
         AND to_jsonb(OLD) - 'is_current' = to_jsonb(NEW) - 'is_current' THEN
        RETURN NEW;
      END IF;
      RAISE EXCEPTION '%: versioned rows are append-only', TG_TABLE_NAME
        USING ERRCODE = 'check_violation';
    END
    $$
    """,
    "CREATE TRIGGER settings_guard BEFORE UPDATE ON core.settings "
    "FOR EACH ROW EXECUTE FUNCTION core.versioned_guard()",
    "CREATE TRIGGER alert_rules_guard BEFORE UPDATE ON core.alert_rules "
    "FOR EACH ROW EXECUTE FUNCTION core.versioned_guard()",
    "CREATE TRIGGER fin_assumptions_guard BEFORE UPDATE ON core.fin_assumptions "
    "FOR EACH ROW EXECUTE FUNCTION core.versioned_guard()",
    "GRANT SELECT, INSERT, DELETE ON stg.batch, stg.rows TO ugk_etl",
    "GRANT USAGE ON SEQUENCE stg.rows_seq_seq TO ugk_etl",
    # Baza nomi qattiq yozilmagan — current_database() orqali (fix r2 keyingi ruling).
    "DO $$ BEGIN "
    "EXECUTE format('GRANT TEMPORARY ON DATABASE %I TO ugk_etl', current_database()); "
    "END $$",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM ugk_etl', current_database()); "
        "END $$"
    )
    for table in ("stg.rows", "stg.batch", "core.fin_assumptions", "core.alert_rules",
                  "core.settings", "core.etl_requests", "core.etl_error", "core.etl_step",
                  "core.etl_run", "core.data_version", "core.builds"):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION core.versioned_guard()")
    op.execute("DROP FUNCTION core.builds_guard()")
