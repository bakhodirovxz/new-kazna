import json
import os
import threading
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.audit.service import (
    GENESIS,
    AuditAction,
    AuditEvent,
    chain_hash,
    ip_aad,
    record,
    ua_aad,
    verify_chain_snapshot,
)
from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session

_APPEND_SQL = (
    "SELECT core.audit_append(:id, :ts, NULL, 'test.x', 'ok', NULL, NULL, NULL, "
    "'{}'::jsonb, NULL, NULL, :chain_key_version, :prev, :hash)"
)


def _reserve(conn: Connection) -> tuple[bytes, int]:
    prev, new_id = conn.execute(
        text("SELECT prev_hash, new_id FROM core.audit_reserve()")
    ).one()
    return bytes(prev), int(new_id)


def _row(audit_id: int) -> dict[str, object]:
    with get_engine("app").connect() as conn:
        return dict(
            conn.execute(
                text(
                    "SELECT *, tableoid::regclass::text AS part "
                    "FROM core.audit_log WHERE id = :i"
                ),
                {"i": audit_id},
            ).mappings().one()
        )


def _month_bounds(months_ago: int) -> tuple[datetime, datetime]:
    """`months_ago` manfiy bo'lishi mumkin (kelajakdagi oy)."""
    now = datetime.now(UTC)
    total = now.year * 12 + (now.month - 1) - months_ago
    y, m = divmod(total, 12)
    start = datetime(y, m + 1, 1, tzinfo=UTC)
    ey, em = divmod(total + 1, 12)
    end = datetime(ey, em + 1, 1, tzinfo=UTC)
    return start, end


def _restore_row(saved: dict[str, object]) -> None:
    cols = ", ".join(saved)
    vals = ", ".join(f"CAST(:{c} AS jsonb)" if c == "details" else f":{c}" for c in saved)
    saved = {**saved, "details": json.dumps(saved["details"])}
    with get_engine("migrator").begin() as conn:
        conn.execute(text(f"INSERT INTO core.audit_log ({cols}) VALUES ({vals})"), saved)


def test_record_stores_encrypted_ip_and_masked_details() -> None:
    audit_id = record(
        AuditEvent(
            action=AuditAction.LOGIN_FAIL,
            result="fail",
            ip="192.168.10.5",
            ua="Mozilla/5.0",
            request_id="r1",
            details={"username": "ali", "password": "hunter2"},
        )
    )
    row = _row(audit_id)
    assert b"192.168.10.5" not in bytes(row["ip_enc"])  # type: ignore[arg-type]
    assert keystore.decrypt_str(Purpose.AUDIT, row["ip_enc"], ip_aad(audit_id)) == "192.168.10.5"  # type: ignore[arg-type]
    assert row["details"] == {"username": "ali", "password": "***"}
    # Oy chegarasida flake bo'lmasligi uchun qatorning o'z `ts`'idan hisoblanadi, datetime.now()
    # emas.
    month = row["ts"].strftime("%Y%m")  # type: ignore[union-attr]
    assert row["part"] == f"core.audit_log_{month}"


def test_ip_ua_aad_follow_global_convention() -> None:
    """Cheap minor (final review): AAD `{schema}.{table}.{column}:{pk}` global konvensiyasiga
    mos bo'lishi kerak — `reencrypt.REENCRYPT_EXEMPT` registridagi ustun nomlari
    (`core.audit_log.ip_enc`/`ua_enc`) bilan bir xil, "ip"/"ua" emas."""
    assert ip_aad(42) == "core.audit_log.ip_enc:42"
    assert ua_aad(42) == "core.audit_log.ua_enc:42"


def test_chain_is_valid_after_records() -> None:
    for _ in range(3):
        record(AuditEvent(action=AuditAction.LOGOUT, user_id=1))
    report = verify_chain_snapshot()
    assert report.ok
    assert report.checked >= 3
    assert report.bad_ids == []


def test_concurrent_records_keep_chain_valid() -> None:
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(10):
                record(AuditEvent(action=AuditAction.LOGOUT))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert verify_chain_snapshot().ok


def test_chain_verifies_across_audit_chain_key_rotation() -> None:
    # KEK buzilganda audit_chain ham rotatsiya qilinadi (key-management.md, П12): eski va yangi
    # versiyali qatorlar aralash zanjirda verify ok, buzilish esa baribir topilishi kerak.
    before = record(AuditEvent(action=AuditAction.LOGOUT, user_id=1))
    old_version = _chain_version(before)
    with get_engine("app").begin() as conn:
        keystore.rotate(conn, get_settings().key_bytes("master_kek"), Purpose.AUDIT_CHAIN)
    keystore.invalidate_keyring()
    after = record(AuditEvent(action=AuditAction.USER_CREATED, details={"n": 1}))
    assert _chain_version(after) > old_version
    report = verify_chain_snapshot()
    assert report.ok and report.bad_ids == []
    with get_engine("migrator").begin() as conn:
        original = conn.execute(
            text("SELECT details FROM core.audit_log WHERE id = :i"), {"i": after}
        ).scalar_one()
        conn.execute(
            text("""UPDATE core.audit_log SET details = '{"n": 2}' WHERE id = :i"""), {"i": after}
        )
    try:
        assert verify_chain_snapshot().bad_ids == [after]
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(
                text("UPDATE core.audit_log SET details = CAST(:d AS jsonb) WHERE id = :i"),
                {"d": json.dumps(original), "i": after},
            )
    assert verify_chain_snapshot().ok


def _chain_version(audit_id: int) -> int:
    with get_engine("migrator").connect() as conn:
        return int(conn.execute(
            text("SELECT chain_key_version FROM core.audit_log WHERE id = :i"), {"i": audit_id}
        ).scalar_one())


def test_tampering_is_detected_and_then_repaired() -> None:
    victim = record(AuditEvent(action=AuditAction.USER_CREATED, details={"username": "x"}))
    record(AuditEvent(action=AuditAction.LOGOUT))
    with get_engine("migrator").begin() as conn:
        original = conn.execute(
            text("SELECT details FROM core.audit_log WHERE id = :i"), {"i": victim}
        ).scalar_one()
        conn.execute(
            text("""UPDATE core.audit_log SET details = '{"username": "y"}' WHERE id = :i"""),
            {"i": victim},
        )
    try:
        report = verify_chain_snapshot()
        assert not report.ok
        assert report.bad_ids == [victim]
        assert report.first_bad_id == victim
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(
                text("UPDATE core.audit_log SET details = CAST(:d AS jsonb) WHERE id = :i"),
                {"d": json.dumps(original), "i": victim},
            )
    assert verify_chain_snapshot().ok


def test_deletion_in_the_middle_is_detected_and_then_repaired() -> None:
    record(AuditEvent(action=AuditAction.LOGOUT))
    victim = record(AuditEvent(action=AuditAction.LOGOUT))
    after = record(AuditEvent(action=AuditAction.LOGOUT))
    with get_engine("migrator").begin() as conn:
        saved = dict(
            conn.execute(text("SELECT * FROM core.audit_log WHERE id = :i"), {"i": victim})
            .mappings().one()
        )
        conn.execute(text("DELETE FROM core.audit_log WHERE id = :i"), {"i": victim})
    try:
        report = verify_chain_snapshot()
        assert not report.ok
        assert after in report.bad_ids
    finally:
        _restore_row(saved)
    assert verify_chain_snapshot().ok


def test_forged_head_is_detected_and_then_repaired() -> None:
    last = record(AuditEvent(action=AuditAction.LOGOUT))
    with get_engine("migrator").begin() as conn:
        original = bytes(
            conn.execute(text("SELECT last_hash FROM core.audit_head WHERE id = 1")).scalar_one()
        )
        conn.execute(
            text("UPDATE core.audit_head SET last_hash = :h WHERE id = 1"), {"h": os.urandom(32)}
        )
    try:
        report = verify_chain_snapshot()
        assert not report.ok
        assert last in report.bad_ids
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(
                text("UPDATE core.audit_head SET last_hash = :h WHERE id = 1"), {"h": original}
            )
    assert verify_chain_snapshot().ok


def test_tampering_in_two_places_reports_both_ids() -> None:
    v1 = record(AuditEvent(action=AuditAction.LOGOUT))
    record(AuditEvent(action=AuditAction.LOGOUT))
    v2 = record(AuditEvent(action=AuditAction.LOGOUT))
    record(AuditEvent(action=AuditAction.LOGOUT))
    with get_engine("migrator").begin() as conn:
        o1 = conn.execute(
            text("SELECT details FROM core.audit_log WHERE id = :i"), {"i": v1}
        ).scalar_one()
        o2 = conn.execute(
            text("SELECT details FROM core.audit_log WHERE id = :i"), {"i": v2}
        ).scalar_one()
        conn.execute(
            text("""UPDATE core.audit_log SET details = '{"x": "1"}' WHERE id = :i"""), {"i": v1}
        )
        conn.execute(
            text("""UPDATE core.audit_log SET details = '{"x": "2"}' WHERE id = :i"""), {"i": v2}
        )
    try:
        report = verify_chain_snapshot()
        assert not report.ok
        assert set(report.bad_ids) >= {v1, v2}
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(
                text("UPDATE core.audit_log SET details = CAST(:d AS jsonb) WHERE id = :i"),
                {"d": json.dumps(o1), "i": v1},
            )
            conn.execute(
                text("UPDATE core.audit_log SET details = CAST(:d AS jsonb) WHERE id = :i"),
                {"d": json.dumps(o2), "i": v2},
            )
    assert verify_chain_snapshot().ok


def test_prefix_deletion_without_anchor_update_is_detected_and_then_repaired() -> None:
    record(AuditEvent(action=AuditAction.LOGOUT))
    with get_engine("migrator").begin() as conn:
        oldest_id = conn.execute(text("SELECT min(id) FROM core.audit_log")).scalar_one()
        saved = dict(
            conn.execute(text("SELECT * FROM core.audit_log WHERE id = :i"), {"i": oldest_id})
            .mappings().one()
        )
        conn.execute(text("DELETE FROM core.audit_log WHERE id = :i"), {"i": oldest_id})
        new_oldest = conn.execute(text("SELECT min(id) FROM core.audit_log")).scalar_one()
    try:
        report = verify_chain_snapshot()
        assert not report.ok
        assert new_oldest in report.bad_ids
    finally:
        _restore_row(saved)
    assert verify_chain_snapshot().ok


def test_unknown_chain_key_version_is_reported_and_verification_continues() -> None:
    # R2-3: bitta qatorning chain_key_version'i noma'lum bo'lsa ham, tekshiruv butunlay
    # to'xtamasligi va zanjirdagi keyingi mustaqil buzilishni ham topa olishi kerak.
    victim = record(AuditEvent(action=AuditAction.LOGOUT))
    record(AuditEvent(action=AuditAction.LOGOUT))
    second_victim = record(AuditEvent(action=AuditAction.USER_CREATED, details={"a": 1}))
    record(AuditEvent(action=AuditAction.LOGOUT))
    with get_engine("migrator").begin() as conn:
        original_version = conn.execute(
            text("SELECT chain_key_version FROM core.audit_log WHERE id = :i"), {"i": victim}
        ).scalar_one()
        conn.execute(
            text("UPDATE core.audit_log SET chain_key_version = 9999 WHERE id = :i"),
            {"i": victim},
        )
        original_details = conn.execute(
            text("SELECT details FROM core.audit_log WHERE id = :i"), {"i": second_victim}
        ).scalar_one()
        conn.execute(
            text("""UPDATE core.audit_log SET details = '{"a": 2}' WHERE id = :i"""),
            {"i": second_victim},
        )
    try:
        report = verify_chain_snapshot()
        assert not report.ok
        assert victim in report.bad_ids
        assert second_victim in report.bad_ids
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(
                text("UPDATE core.audit_log SET chain_key_version = :v WHERE id = :i"),
                {"v": original_version, "i": victim},
            )
            conn.execute(
                text("UPDATE core.audit_log SET details = CAST(:d AS jsonb) WHERE id = :i"),
                {"d": json.dumps(original_details), "i": second_victim},
            )
    assert verify_chain_snapshot().ok


def test_app_role_cannot_write_audit_tables_directly() -> None:
    record(AuditEvent(action=AuditAction.LOGOUT))
    with get_engine("app").connect() as conn:
        partition = conn.execute(
            text(
                "SELECT inhrelid::regclass::text FROM pg_inherits "
                "WHERE inhparent = 'core.audit_log'::regclass "
                "AND inhrelid::regclass::text ~ 'audit_log_[0-9]{6}$' LIMIT 1"
            )
        ).scalar_one()
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("INSERT INTO core.audit_log (id) VALUES (999999999)"))
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("UPDATE core.audit_head SET last_id = last_id"))
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text(f"UPDATE {partition} SET result = 'ok'"))
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text(f"DELETE FROM {partition}"))


def test_app_role_cannot_write_audit_anchor() -> None:
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(
            text("INSERT INTO core.audit_anchor (id, last_dropped_hash) VALUES (2, :h)"),
            {"h": os.urandom(32)},
        )
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("UPDATE core.audit_anchor SET last_dropped_id = last_dropped_id"))


def test_app_role_cannot_setval_audit_sequence() -> None:
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("SELECT setval('core.audit_log_id_seq', 1)"))


def test_etl_role_cannot_select_audit_log() -> None:
    with (
        get_engine("etl").connect() as conn,
        pytest.raises(ProgrammingError, match="permission denied"),
    ):
        conn.execute(text("SELECT count(*) FROM core.audit_log"))


def test_audit_append_rejects_wrong_prev_hash() -> None:
    # `audit_reserve()` avval chaqiriladi — shu bilan p_id currval() talabini qanoatlantiradi,
    # shunda xato aniq prev_hash tekshiruvidan kelishi kafolatlanadi (R2-2 boshqa tekshiruvlar
    # bilan aralashib ketmasin).
    with get_engine("app").begin() as conn, pytest.raises(DBAPIError):
        _prev, new_id = _reserve(conn)
        conn.execute(
            text(_APPEND_SQL),
            {
                "id": new_id,
                "ts": datetime.now(UTC),
                "chain_key_version": 1,
                "prev": os.urandom(32),
                "hash": os.urandom(32),
            },
        )


def test_audit_append_rejects_id_not_matching_reserved_sequence() -> None:
    with get_engine("app").begin() as conn, pytest.raises(DBAPIError):
        prev, new_id = _reserve(conn)
        conn.execute(
            text(_APPEND_SQL),
            {
                "id": new_id + 1,
                "ts": datetime.now(UTC),
                "chain_key_version": 1,
                "prev": prev,
                "hash": os.urandom(32),
            },
        )


def test_audit_append_rejects_ts_far_from_now() -> None:
    with get_engine("app").begin() as conn, pytest.raises(DBAPIError):
        prev, new_id = _reserve(conn)
        conn.execute(
            text(_APPEND_SQL),
            {
                "id": new_id,
                "ts": datetime.now(UTC) - timedelta(days=1),
                "chain_key_version": 1,
                "prev": prev,
                "hash": os.urandom(32),
            },
        )


def test_audit_append_rejects_unknown_chain_key_version() -> None:
    with get_engine("app").begin() as conn, pytest.raises(DBAPIError):
        prev, new_id = _reserve(conn)
        conn.execute(
            text(_APPEND_SQL),
            {
                "id": new_id,
                "ts": datetime.now(UTC),
                "chain_key_version": 9999,
                "prev": prev,
                "hash": os.urandom(32),
            },
        )


def test_record_still_works_after_audit_append_hardening() -> None:
    audit_id = record(AuditEvent(action=AuditAction.LOGOUT))
    assert verify_chain_snapshot().ok
    row = _row(audit_id)
    assert row["id"] == audit_id


def test_record_with_etl_role_works() -> None:
    audit_id = record(AuditEvent(action=AuditAction.LOGOUT), role="etl")
    assert verify_chain_snapshot().ok
    with get_engine("migrator").connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM core.audit_log WHERE id = :i"), {"i": audit_id}
        ).scalar_one()
    assert count == 1


def test_sanitizes_hostile_details_and_still_verifies() -> None:
    audit_id = record(
        AuditEvent(
            action=AuditAction.USER_UPDATED,
            details={
                "nul": "a\x00b",
                "big_float": 1e16,
                "nan": float("nan"),
                "amount": Decimal("12.50"),
                "id": uuid.uuid4(),
                "when": datetime.now(UTC),
            },
        )
    )
    row = _row(audit_id)
    details = row["details"]
    assert isinstance(details, dict)
    assert "\x00" not in json.dumps(details)
    assert isinstance(details["big_float"], str)
    assert isinstance(details["nan"], str)
    assert isinstance(details["amount"], str)
    assert isinstance(details["id"], str)
    assert isinstance(details["when"], str)
    assert verify_chain_snapshot().ok


def test_truncates_overlong_object_id() -> None:
    audit_id = record(AuditEvent(action=AuditAction.USER_UPDATED, object_id="x" * 200))
    row = _row(audit_id)
    assert row["object_id"] == "x" * 64
    assert verify_chain_snapshot().ok


def test_sanitizes_nul_in_details_keys() -> None:
    # R2-1: `_sanitize` kalitlarni ham tozalashi kerak — NUL bo'lgan kalit jsonb yozishda
    # xato beradi.
    audit_id = record(AuditEvent(action=AuditAction.USER_UPDATED, details={"a\x00": 1}))
    row = _row(audit_id)
    assert row["details"] == {"a": 1}
    assert verify_chain_snapshot().ok


def test_sanitizes_lone_surrogate_in_details_value() -> None:
    # R2-1: yolg'on surrogate (masalan, so'rov tanasidan noto'g'ri UTF-16 juftlikdan hosil
    # bo'lgan) qiymat UTF-8'ga kodlashda yiqilib tushmasligi kerak.
    audit_id = record(AuditEvent(action=AuditAction.USER_UPDATED, details={"k": "\ud800"}))
    row = _row(audit_id)
    details = row["details"]
    assert isinstance(details, dict)
    # Python'ning standart UTF-8 "replace" kodlash xato ishlovchisi noto'g'ri belgini
    # ASCII "?" (0x3F) bilan almashtiradi (dekodlashdagi U+FFFD'dan farqli) — muhimi,
    # asl surrogate saqlanib qolmaydi va qiymat xavfsiz UTF-8 satrga aylanadi.
    assert details["k"] == "?"
    assert verify_chain_snapshot().ok


def test_sanitizes_lone_surrogate_in_object_id() -> None:
    audit_id = record(AuditEvent(action=AuditAction.USER_UPDATED, object_id="\ud800x"))
    row = _row(audit_id)
    assert row["object_id"] == "?x"
    assert verify_chain_snapshot().ok


def test_drop_old_partitions_respects_12_month_floor() -> None:
    with get_engine("etl").begin() as conn:
        dropped_zero = conn.execute(text("SELECT core.drop_old_audit_partitions(0)")).scalar_one()
        dropped_neg = conn.execute(
            text("SELECT core.drop_old_audit_partitions(-1)")
        ).scalar_one()
    assert dropped_zero == 0
    assert dropped_neg == 0


def test_drop_old_partitions_floor_protects_recent_old_partition() -> None:
    # R2-4: 12 oylik pol argumentga qaramay amal qilishi kerak — 6 oylik (hali "eski"
    # bo'lmagan) partitsiya keep_months=0 bilan ham o'chirilmasin.
    start, end = _month_bounds(months_ago=6)
    table = f"audit_log_{start.strftime('%Y%m')}"
    with get_engine("migrator").begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS core.{table}"))
        conn.execute(
            text(
                f"CREATE TABLE core.{table} PARTITION OF core.audit_log "
                f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
            )
        )
    try:
        with get_engine("etl").begin() as conn:
            dropped = conn.execute(text("SELECT core.drop_old_audit_partitions(0)")).scalar_one()
        assert dropped == 0
        with get_engine("migrator").connect() as conn:
            regclass = conn.execute(text("SELECT to_regclass(:t)"), {"t": f"core.{table}"}).scalar()
        assert regclass is not None
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS core.{table}"))


def test_drop_old_partitions_updates_anchor_to_dropped_rows_hash() -> None:
    # To'liq, jamlanuvchi (session bo'yicha umumiy) zanjirga 14 oy oldingi haqiqiy bog'langan
    # qatorni "to'qish" amalda murakkab va mo'rt (task-6-findings-r1.md F4 izohi buni tan oladi).
    # Eng yaqin haqiqiy variant: mustaqil, o'zi ichida izchil (to'g'ri HMAC) bitta qatorli eski
    # partitsiya yaratamiz, uni core.drop_old_audit_partitions bilan o'chiramiz va anchor
    # ANIQ shu qatorning hash'iga yangilanganini tekshiramiz — bu funksiyaning anchor-yangilash
    # mantig'ini to'g'ridan-to'g'ri isbotlaydi (butun jamlanuvchi zanjirni oxirigacha
    # tekshirmasdan).
    start, end = _month_bounds(months_ago=14)
    table = f"audit_log_{start.strftime('%Y%m')}"
    version, key = keystore.hmac_key(Purpose.AUDIT_CHAIN)
    synth_id = 900_000_001
    row: dict[str, object] = {
        "id": synth_id, "ts": start, "user_id": None, "action": "test.marker", "result": "ok",
        "object_type": None, "object_id": None, "request_id": None, "details": {},
        "ip_enc": None, "ua_enc": None, "chain_key_version": version,
    }
    synth_hash = chain_hash(key, GENESIS, row)
    with get_engine("migrator").begin() as conn:
        before = dict(
            conn.execute(
                text(
                    "SELECT last_dropped_id, last_dropped_hash FROM core.audit_anchor WHERE id = 1"
                )
            ).mappings().one()
        )
        # PARTITION OF ... FOR VALUES chegaralari bog'lash parametrlarini qabul qilmaydi —
        # Postgres bu qiymatlarni DDL vaqtida literal sifatida kutadi.
        conn.execute(
            text(
                f"CREATE TABLE core.{table} PARTITION OF core.audit_log "
                f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
            )
        )
        params = {
            **row, "details": json.dumps(row["details"]), "prev_hash": GENESIS, "hash": synth_hash,
        }
        conn.execute(
            text(
                "INSERT INTO core.audit_log (id, ts, user_id, action, result, object_type, "
                "object_id, request_id, details, ip_enc, ua_enc, chain_key_version, "
                "prev_hash, hash) VALUES (:id, :ts, :user_id, :action, :result, :object_type, "
                ":object_id, :request_id, CAST(:details AS jsonb), :ip_enc, :ua_enc, "
                ":chain_key_version, :prev_hash, :hash)"
            ),
            params,
        )
    try:
        with get_engine("etl").begin() as conn:
            dropped = conn.execute(text("SELECT core.drop_old_audit_partitions(12)")).scalar_one()
        assert dropped >= 1
        with get_engine("migrator").connect() as conn:
            regclass = conn.execute(text("SELECT to_regclass(:t)"), {"t": f"core.{table}"}).scalar()
            assert regclass is None
            anchor = dict(
                conn.execute(
                    text(
                        "SELECT last_dropped_id, last_dropped_hash "
                        "FROM core.audit_anchor WHERE id = 1"
                    )
                ).mappings().one()
            )
        assert anchor["last_dropped_id"] == synth_id
        assert bytes(anchor["last_dropped_hash"]) == synth_hash  # type: ignore[arg-type]
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(
                text(
                    "UPDATE core.audit_anchor SET last_dropped_id = :id, "
                    "last_dropped_hash = :h WHERE id = 1"
                ),
                {"id": before["last_dropped_id"], "h": bytes(before["last_dropped_hash"])},  # type: ignore[arg-type]
            )


def test_ensure_audit_partitions_moves_default_rows_into_new_partition() -> None:
    start, _ = _month_bounds(months_ago=-5)  # 5 oy kelajakda — hozirgi ufqdan (3) tashqarida
    table = f"audit_log_{start.strftime('%Y%m')}"
    version, key = keystore.hmac_key(Purpose.AUDIT_CHAIN)
    synth_id = 900_000_002
    row: dict[str, object] = {
        "id": synth_id, "ts": start, "user_id": None, "action": "test.future", "result": "ok",
        "object_type": None, "object_id": None, "request_id": None, "details": {},
        "ip_enc": None, "ua_enc": None, "chain_key_version": version,
    }
    synth_hash = chain_hash(key, GENESIS, row)
    with get_engine("migrator").begin() as conn:
        # Bu partitsiya avvalgi (DB qayta yaratilmagan) test yugurishidan qolgan bo'lishi
        # mumkin — testni takroriy yugurishlarga mustahkam qilish uchun oldindan tozalanadi.
        conn.execute(text(f"DROP TABLE IF EXISTS core.{table}"))
        params = {
            **row, "details": json.dumps(row["details"]), "prev_hash": GENESIS, "hash": synth_hash,
        }
        conn.execute(
            text(
                "INSERT INTO core.audit_log_default (id, ts, user_id, action, result, "
                "object_type, object_id, request_id, details, ip_enc, ua_enc, "
                "chain_key_version, prev_hash, hash) VALUES (:id, :ts, :user_id, :action, "
                ":result, :object_type, :object_id, :request_id, CAST(:details AS jsonb), "
                ":ip_enc, :ua_enc, :chain_key_version, :prev_hash, :hash)"
            ),
            params,
        )
    try:
        with get_engine("app").begin() as conn:
            conn.execute(text("SELECT core.ensure_audit_partitions(6)"))
        with get_engine("migrator").connect() as conn:
            partition = conn.execute(
                text("SELECT tableoid::regclass::text FROM core.audit_log WHERE id = :i"),
                {"i": synth_id},
            ).scalar_one()
            still_in_default = conn.execute(
                text("SELECT count(*) FROM ONLY core.audit_log_default WHERE id = :i"),
                {"i": synth_id},
            ).scalar_one()
        assert partition == f"core.{table}"
        assert still_in_default == 0
    finally:
        # `ensure_audit_partitions` yaratgan partitsiya ishlab chiqarishda doimiy qoladi;
        # testni takroriy (DB qayta yaratilmagan) yugurishlar uchun toza holatda qoldiramiz.
        with get_engine("migrator").begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS core.{table}"))


def test_partitions_exist_for_next_months() -> None:
    with get_engine("app").begin() as conn:
        conn.execute(text("SELECT core.ensure_audit_partitions(3)"))
        count = conn.execute(
            text(
                "SELECT count(*) FROM pg_inherits WHERE inhparent = 'core.audit_log'::regclass "
                "AND inhrelid::regclass::text ~ 'audit_log_[0-9]{6}$'"
            )
        ).scalar_one()
    assert count >= 4
