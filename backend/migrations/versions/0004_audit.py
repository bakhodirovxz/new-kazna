"""audit jurnali: oylik partitsiyalar, hash-chain boshi

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-24
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

STATEMENTS = [
    "CREATE SEQUENCE core.audit_log_id_seq",
    """
    CREATE TABLE core.audit_log (
      id bigint NOT NULL,
      ts timestamptz NOT NULL,
      user_id bigint,
      action varchar(64) NOT NULL,
      result varchar(8) NOT NULL CHECK (result IN ('ok', 'fail', 'denied')),
      object_type varchar(32),
      object_id varchar(64),
      request_id varchar(32),
      details jsonb NOT NULL DEFAULT '{}'::jsonb,
      ip_enc bytea,
      ua_enc bytea,
      prev_hash bytea NOT NULL,
      hash bytea NOT NULL,
      PRIMARY KEY (id, ts)
    ) PARTITION BY RANGE (ts)
    """,
    "CREATE TABLE core.audit_log_default PARTITION OF core.audit_log DEFAULT",
    "CREATE INDEX audit_log_id_idx ON core.audit_log (id)",
    "CREATE INDEX audit_log_ts_idx ON core.audit_log (ts)",
    "CREATE INDEX audit_log_user_ts_idx ON core.audit_log (user_id, ts)",
    "CREATE INDEX audit_log_action_ts_idx ON core.audit_log (action, ts)",
    """
    CREATE TABLE core.audit_head (
      id smallint PRIMARY KEY CHECK (id = 1),
      last_id bigint,
      last_hash bytea NOT NULL
    )
    """,
    "INSERT INTO core.audit_head (id, last_id, last_hash) VALUES (1, NULL, decode(repeat('00', 32), 'hex'))",
    """
    CREATE FUNCTION core.ensure_audit_partitions(months_ahead integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, core AS $$
    DECLARE
      base date := date_trunc('month', now() AT TIME ZONE 'UTC')::date;
      created integer := 0;
      part text;
      start_ts timestamptz;
      end_ts timestamptz;
    BEGIN
      FOR i IN 0..months_ahead LOOP
        part := 'audit_log_' || to_char(base + make_interval(months => i), 'YYYYMM');
        IF to_regclass('core.' || part) IS NULL THEN
          start_ts := (base + make_interval(months => i)) AT TIME ZONE 'UTC';
          end_ts := (base + make_interval(months => i + 1)) AT TIME ZONE 'UTC';
          EXECUTE format(
            'CREATE TABLE core.%I PARTITION OF core.audit_log FOR VALUES FROM (%L) TO (%L)',
            part, start_ts, end_ts);
          created := created + 1;
        END IF;
      END LOOP;
      RETURN created;
    END
    $$
    """,
    """
    CREATE FUNCTION core.drop_old_audit_partitions(keep_months integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, core AS $$
    DECLARE
      cutoff date := (date_trunc('month', now() AT TIME ZONE 'UTC')
                      - make_interval(months => keep_months))::date;
      dropped integer := 0;
      r record;
    BEGIN
      FOR r IN
        SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
        WHERE i.inhparent = 'core.audit_log'::regclass AND c.relname ~ '^audit_log_[0-9]{6}$'
      LOOP
        IF to_date(substr(r.relname, 11), 'YYYYMM') < cutoff THEN
          EXECUTE format('DROP TABLE core.%I', r.relname);
          dropped := dropped + 1;
        END IF;
      END LOOP;
      RETURN dropped;
    END
    $$
    """,
    "REVOKE ALL ON FUNCTION core.ensure_audit_partitions(integer) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION core.drop_old_audit_partitions(integer) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION core.ensure_audit_partitions(integer) TO ugk_app, ugk_etl",
    "GRANT EXECUTE ON FUNCTION core.drop_old_audit_partitions(integer) TO ugk_etl",
    "SELECT core.ensure_audit_partitions(3)",
    # Faqat qo'shish: UPDATE/DELETE hech kimga berilmaydi.
    "GRANT SELECT, INSERT ON core.audit_log TO ugk_app, ugk_etl",
    "GRANT SELECT, UPDATE ON core.audit_head TO ugk_app, ugk_etl",
    "GRANT USAGE ON SEQUENCE core.audit_log_id_seq TO ugk_app, ugk_etl",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP FUNCTION core.drop_old_audit_partitions(integer)")
    op.execute("DROP FUNCTION core.ensure_audit_partitions(integer)")
    op.execute("DROP TABLE core.audit_head")
    op.execute("DROP TABLE core.audit_log")
    op.execute("DROP SEQUENCE core.audit_log_id_seq")
