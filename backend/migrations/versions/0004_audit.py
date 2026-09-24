"""audit jurnali: oylik partitsiyalar, kalitlangan (HMAC) hash-chain boshi, anchor

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-24

Fix round 1 (task-6-findings-r1.md) o'zgarishlari shu migratsiyaga to'g'ridan-to'g'ri
kiritildi — hali hech narsa deploy qilinmagan:
  F1: `chain_key_version` ustuni — zanjir endi HMAC-SHA256(chain_key[v], prev||canonical) bilan.
  F2: `ugk_app`/`ugk_etl` endi `audit_log`/`audit_head` ustida to'g'ridan-to'g'ri yozish huquqiga
      ega emas — faqat `core.audit_reserve()`/`core.audit_append()` SECURITY DEFINER funksiyalari
      orqali (ikkalasi ham egasi — `ugk_migrator` — nomidan ishlaydi).
  F3: `core.audit_anchor` — zanjir boshlanishi (eskirgan partitsiyalar o'chirilganda ham
      `verify_chain` uzluksiz tekshira olishi uchun).
  F4: `drop_old_audit_partitions` — minimal 12 oy saqlash chegarasi + partitsiya
      o'chirishdan oldin anchor'ni yangilaydi.
  F6: `ensure_audit_partitions` — oralig'i cheklangan (0..24) va default partitsiyadagi
      mos qatorlarni yangi partitsiyaga xavfsiz ko'chiradi.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# To'liq (nom + tur) imzo — CREATE, REVOKE, GRANT va DROP FUNCTION'da bir xil ishlatiladi
# (Postgres bu buyruqlarda parametr nomlarini qabul qiladi, moslashtirish faqat turlar bo'yicha).
AUDIT_APPEND_SIG = (
    "core.audit_append(p_id bigint, p_ts timestamptz, p_user_id bigint, p_action text, "
    "p_result text, p_object_type text, p_object_id text, p_request_id text, "
    "p_details jsonb, p_ip_enc bytea, p_ua_enc bytea, p_chain_key_version smallint, "
    "p_prev_hash bytea, p_hash bytea)"
)

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
      chain_key_version smallint NOT NULL,
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
    # F3: zanjir "boshlanishi" — eng eski (hali tirik) qatorning prev_hash'i shunga teng bo'lishi
    # kerak. Partitsiya o'chirilganda (F4) shu yerga yangilanadi; boshqacha hech kim yozmaydi.
    """
    CREATE TABLE core.audit_anchor (
      id smallint PRIMARY KEY CHECK (id = 1),
      last_dropped_id bigint,
      last_dropped_hash bytea NOT NULL
    )
    """,
    "INSERT INTO core.audit_anchor (id, last_dropped_id, last_dropped_hash) "
    "VALUES (1, NULL, decode(repeat('00', 32), 'hex'))",
    # F6: partitsiya yaratish — oraliq 0..24 oy bilan cheklanadi; agar default partitsiyada
    # yangi oraliqqa tushadigan qatorlar bo'lsa (masalan, kelajakdagi voqea oldindan yozilgan
    # bo'lsa), default vaqtincha ajratiladi, qatorlar yangi partitsiyaga ko'chiriladi, so'ng
    # default qayta biriktiriladi.
    """
    CREATE FUNCTION core.ensure_audit_partitions(months_ahead integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
      eff_months integer := LEAST(GREATEST(months_ahead, 0), 24);
      base date := pg_catalog.date_trunc('month', pg_catalog.now() AT TIME ZONE 'UTC')::date;
      created integer := 0;
      part text;
      start_ts timestamptz;
      end_ts timestamptz;
      moved bigint;
    BEGIN
      FOR i IN 0..eff_months LOOP
        part := 'audit_log_' ||
          pg_catalog.to_char(base + pg_catalog.make_interval(months => i), 'YYYYMM');
        IF pg_catalog.to_regclass('core.' || part) IS NULL THEN
          start_ts := (base + pg_catalog.make_interval(months => i)) AT TIME ZONE 'UTC';
          end_ts := (base + pg_catalog.make_interval(months => i + 1)) AT TIME ZONE 'UTC';

          EXECUTE pg_catalog.format(
            'SELECT count(*) FROM core.audit_log_default WHERE ts >= %L AND ts < %L',
            start_ts, end_ts) INTO moved;

          IF moved > 0 THEN
            ALTER TABLE core.audit_log DETACH PARTITION core.audit_log_default;
          END IF;

          EXECUTE pg_catalog.format(
            'CREATE TABLE core.%I PARTITION OF core.audit_log FOR VALUES FROM (%L) TO (%L)',
            part, start_ts, end_ts);
          created := created + 1;

          IF moved > 0 THEN
            EXECUTE pg_catalog.format(
              'INSERT INTO core.%I SELECT * FROM core.audit_log_default '
              'WHERE ts >= %L AND ts < %L',
              part, start_ts, end_ts);
            EXECUTE pg_catalog.format(
              'DELETE FROM core.audit_log_default WHERE ts >= %L AND ts < %L',
              start_ts, end_ts);
            ALTER TABLE core.audit_log ATTACH PARTITION core.audit_log_default DEFAULT;
          END IF;
        END IF;
      END LOOP;
      RETURN created;
    END
    $$
    """,
    # F4: samarali saqlash muddati hech qachon 12 oydan kam bo'lmaydi. Partitsiya
    # o'chirilishidan oldin (eng eskisidan boshlab) `audit_anchor` o'sha partitsiyadagi eng
    # so'nggi (max id) qatorning hash'iga yangilanadi — shu orqali qolgan zanjir tekshiruvi
    # uzluksiz bo'lib qoladi.
    """
    CREATE FUNCTION core.drop_old_audit_partitions(keep_months integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
      eff_keep integer := GREATEST(keep_months, 12);
      cutoff date := (pg_catalog.date_trunc('month', pg_catalog.now() AT TIME ZONE 'UTC')
                      - pg_catalog.make_interval(months => eff_keep))::date;
      dropped integer := 0;
      r record;
      max_id bigint;
      max_hash bytea;
    BEGIN
      FOR r IN
        SELECT c.relname FROM pg_catalog.pg_inherits i
        JOIN pg_catalog.pg_class c ON c.oid = i.inhrelid
        WHERE i.inhparent = 'core.audit_log'::regclass AND c.relname ~ '^audit_log_[0-9]{6}$'
        ORDER BY c.relname
      LOOP
        IF pg_catalog.to_date(pg_catalog.substr(r.relname, 11), 'YYYYMM') < cutoff THEN
          EXECUTE pg_catalog.format('SELECT max(id) FROM core.%I', r.relname) INTO max_id;
          IF max_id IS NOT NULL THEN
            EXECUTE pg_catalog.format('SELECT hash FROM core.%I WHERE id = $1', r.relname)
              INTO max_hash USING max_id;
            UPDATE core.audit_anchor SET last_dropped_id = max_id, last_dropped_hash = max_hash
              WHERE id = 1;
          END IF;
          EXECUTE pg_catalog.format('DROP TABLE core.%I', r.relname);
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
    # F2: yagona yozish yo'li. `audit_reserve()` navbatdagi id'ni va joriy zanjir boshini
    # zaxiralaydi (FOR UPDATE qulfi chaqiruvchi tranzaksiya yakunlanguncha ushlab turiladi —
    # bu funksiya alohida tranzaksiyada emas, chaqiruvchining tranzaksiyasida bajariladi).
    # `audit_append()` boshni qayta tekshiradi (bo'shashgan holatda RAISE) va bitta amalda
    # qator qo'shib, boshni yangilaydi.
    """
    CREATE FUNCTION core.audit_reserve() RETURNS TABLE(prev_hash bytea, new_id bigint)
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    BEGIN
      RETURN QUERY
      SELECT h.last_hash, nextval('core.audit_log_id_seq')::bigint
      FROM core.audit_head h WHERE h.id = 1 FOR UPDATE;
    END
    $$
    """,
    # R2-2: caller-chosen p_id/p_ts/p_chain_key_version endi qattiq tekshiriladi — aks holda
    # (a) o'zboshimcha p_id (masalan, bigint maksimumi) barcha kelajakdagi yozuvlarni
    # abadiy "not monotonic" bilan bloklab qo'yishi mumkin, (b) o'zboshimcha p_ts eski
    # partitsiyaga tushib, retention anchor'ini chalkashtirishi mumkin, (c) noma'lum
    # chain_key_version qatorni umuman tekshirib bo'lmaydigan qilib qo'yadi.
    f"""
    CREATE FUNCTION {AUDIT_APPEND_SIG} RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
      cur_last_id bigint;
      cur_last_hash bytea;
      reserved_id bigint;
    BEGIN
      SELECT h.last_id, h.last_hash INTO cur_last_id, cur_last_hash
      FROM core.audit_head h WHERE h.id = 1 FOR UPDATE;

      -- p_id shu SESSIYAda avvalroq audit_reserve() chaqirgan nextval()'ga bog'lanadi;
      -- agar bu sessiyada hali nextval() chaqirilmagan bo'lsa, currval() o'zi xato beradi.
      reserved_id := pg_catalog.currval('core.audit_log_id_seq');
      IF p_id <> reserved_id THEN
        RAISE EXCEPTION 'audit id does not match reserved sequence value';
      END IF;

      IF cur_last_hash <> p_prev_hash THEN
        RAISE EXCEPTION 'audit chain head mismatch';
      END IF;
      IF cur_last_id IS NOT NULL AND p_id <= cur_last_id THEN
        RAISE EXCEPTION 'audit id not monotonic';
      END IF;

      IF p_ts < pg_catalog.clock_timestamp() - interval '5 minutes'
         OR p_ts > pg_catalog.clock_timestamp() + interval '5 minutes' THEN
        RAISE EXCEPTION 'audit ts out of bounds';
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM core.crypto_keys
        WHERE purpose = 'audit_chain' AND version = p_chain_key_version
          AND status IN ('active', 'decrypt_only')
      ) THEN
        RAISE EXCEPTION 'unknown audit chain key version';
      END IF;

      INSERT INTO core.audit_log (
        id, ts, user_id, action, result, object_type, object_id, request_id, details,
        ip_enc, ua_enc, chain_key_version, prev_hash, hash
      ) VALUES (
        p_id, p_ts, p_user_id, p_action, p_result, p_object_type, p_object_id, p_request_id,
        p_details, p_ip_enc, p_ua_enc, p_chain_key_version, p_prev_hash, p_hash
      );
      UPDATE core.audit_head SET last_id = p_id, last_hash = p_hash WHERE id = 1;
    END
    $$
    """,
    "REVOKE ALL ON FUNCTION core.audit_reserve() FROM PUBLIC",
    f"REVOKE ALL ON FUNCTION {AUDIT_APPEND_SIG} FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION core.audit_reserve() TO ugk_app, ugk_etl",
    f"GRANT EXECUTE ON FUNCTION {AUDIT_APPEND_SIG} TO ugk_app, ugk_etl",
    # Faqat o'qish: yozish faqat yuqoridagi SECURITY DEFINER funksiyalari orqali (ular egasi —
    # ugk_migrator — nomidan ishlaydi). ugk_app audit/admin API o'qishlari uchun SELECT oladi
    # (Task 12: `audit:read`); ugk_etl hech qanday to'g'ridan-to'g'ri jadval huquqiga ega emas.
    "GRANT SELECT ON core.audit_log TO ugk_app",
    "GRANT SELECT ON core.audit_head TO ugk_app",
    "GRANT SELECT ON core.audit_anchor TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {AUDIT_APPEND_SIG}")
    op.execute("DROP FUNCTION core.audit_reserve()")
    op.execute("DROP FUNCTION core.drop_old_audit_partitions(integer)")
    op.execute("DROP FUNCTION core.ensure_audit_partitions(integer)")
    op.execute("DROP TABLE core.audit_anchor")
    op.execute("DROP TABLE core.audit_head")
    op.execute("DROP TABLE core.audit_log")
    op.execute("DROP SEQUENCE core.audit_log_id_seq")
