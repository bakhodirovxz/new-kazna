import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.audit.service import AuditAction, AuditEvent, ip_aad, record, verify_chain_snapshot
from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session


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
    month = datetime.now(UTC).strftime("%Y%m")
    assert row["part"] == f"core.audit_log_{month}"


def test_chain_is_valid_after_records() -> None:
    for _ in range(3):
        record(AuditEvent(action=AuditAction.LOGOUT, user_id=1))
    report = verify_chain_snapshot()
    assert report.ok
    assert report.checked >= 3


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
        assert report.first_bad_id == victim
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(
                text("UPDATE core.audit_log SET details = CAST(:d AS jsonb) WHERE id = :i"),
                {"d": __import__("json").dumps(original), "i": victim},
            )
    assert verify_chain_snapshot().ok


def test_deleting_tail_is_detected() -> None:
    last = record(AuditEvent(action=AuditAction.LOGOUT))
    with get_engine("migrator").begin() as conn:
        saved = dict(
            conn.execute(text("SELECT * FROM core.audit_log WHERE id = :i"), {"i": last})
            .mappings().one()
        )
        conn.execute(text("DELETE FROM core.audit_log WHERE id = :i"), {"i": last})
    try:
        assert not verify_chain_snapshot().ok
    finally:
        cols = ", ".join(saved)
        vals = ", ".join(
            f"CAST(:{c} AS jsonb)" if c == "details" else f":{c}" for c in saved
        )
        saved["details"] = __import__("json").dumps(saved["details"])
        with get_engine("migrator").begin() as conn:
            conn.execute(
                text(f"INSERT INTO core.audit_log ({cols}) VALUES ({vals})"),  # noqa: S608
                saved,
            )
    assert verify_chain_snapshot().ok


def test_app_role_cannot_update_or_delete_audit() -> None:
    record(AuditEvent(action=AuditAction.LOGOUT))
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("UPDATE core.audit_log SET result = 'ok'"))
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("DELETE FROM core.audit_log"))


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
