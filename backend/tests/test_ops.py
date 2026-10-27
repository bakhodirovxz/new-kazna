import base64
import contextlib
import io
import json
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import cli, devtools, ops
from app.core import keystore
from app.core.config import get_settings
from app.core.db import get_engine
from app.main import create_app
from tests.etl_helpers import RecordingNotifier
from tests.helpers import SeedUser, login

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def _result(**overrides: Any) -> ops.RestoreResult:
    base: dict[str, Any] = {
        "at": NOW, "result": "ok", "duration_seconds": 1800,
        "backup": "20260925-200000F", "details": "core.users 5;",
    }
    return ops.RestoreResult(**{**base, **overrides})


@pytest.fixture
def clean_restore_setting() -> Iterator[None]:
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.settings WHERE key = :k"), {"k": ops.RESTORE_KEY})


def _audit_count(action: str) -> int:
    with get_engine("app").connect() as conn:
        return int(conn.execute(
            text(
                "SELECT count(*) FROM core.audit_log "
                "WHERE action = :a AND details->>'via' = 'cli'"
            ),
            {"a": action},
        ).scalar_one())


def _cert(tmp_path: Path, days: int) -> Path:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ugk.test")])
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - timedelta(days=1)).not_valid_after(NOW + timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    path = tmp_path / f"cert-{days}.pem"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return path


def test_record_restore_test_versions(clean_restore_setting: None) -> None:
    with get_engine("app").begin() as conn:
        assert ops.record_restore_test(conn, _result(result="fail")) == 1
        assert ops.record_restore_test(conn, _result(duration_seconds=9000)) == 2
        value = ops.last_restore_test(conn)
    assert value is not None
    assert value["result"] == "ok"
    assert value["duration_seconds"] == 9000
    assert value["rto_ok"] is False
    assert value["backup"] == "20260925-200000F"


def test_restore_setting_not_editable_via_api(
    clean_restore_setting: None, make_user: Callable[..., SeedUser]
) -> None:
    with TestClient(create_app(), base_url="https://testserver") as client:
        login(client, make_user("admin"))
        response = client.put(
            "/api/v1/admin/settings/last_restore_test", json={"value": {"result": "ok"}}
        )
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("value", "codes"),
    [
        (None, {"restore_test_missing"}),
        ({"at": NOW.isoformat(), "result": "ok", "rto_ok": True}, set()),
        ({"at": NOW.isoformat(), "result": "fail", "rto_ok": True}, {"restore_test_failed"}),
        ({"at": (NOW - timedelta(days=41)).isoformat(), "result": "ok", "rto_ok": True},
         {"restore_test_overdue"}),
        # 35-дневный интервал между таймерами не даёт ложного предупреждения
        ({"at": (NOW - timedelta(days=36)).isoformat(), "result": "ok", "rto_ok": True}, set()),
        ({"at": NOW.isoformat(), "result": "ok", "rto_ok": False}, {"restore_test_rto"}),
    ],
)
def test_check_restore_rules(value: dict[str, Any] | None, codes: set[str]) -> None:
    assert {p.code for p in ops.check_restore(value, NOW)} == codes


def test_ops_check_detects_clock_skew() -> None:
    skewed = ops.ops_check(app_clock=lambda: datetime.now(UTC) + timedelta(minutes=10))
    found = [p for p in skewed if p.code == "clock_skew"]
    assert found and found[0].level == "critical"
    assert "clock_skew" not in {p.code for p in ops.ops_check()}


def test_ops_check_flags_audit_default_rows() -> None:
    row = {"id": 9_000_000_001, "ts": datetime(2001, 1, 1, tzinfo=UTC)}
    with get_engine("migrator").begin() as conn:
        conn.execute(
            text(
                "INSERT INTO core.audit_log "
                "(id, ts, action, result, chain_key_version, prev_hash, hash) "
                "VALUES (:id, :ts, 'test.default', 'ok', 1, decode(repeat('00', 32), 'hex'), "
                "decode(repeat('00', 32), 'hex'))"
            ),
            row,
        )
    try:
        assert "audit_default_rows" in {p.code for p in ops.ops_check()}
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(text("DELETE FROM core.audit_log WHERE id = :id"), {"id": row["id"]})


def test_ops_check_flags_stuck_etl_requests() -> None:
    with get_engine("migrator").begin() as conn:
        request_id = conn.execute(text(
            "INSERT INTO core.etl_requests (source, mode, requested_by, requested_at) "
            "VALUES ('synthetic', 'full', 0, now() - interval '2 hours') RETURNING id"
        )).scalar_one()
    try:
        assert "etl_request_stuck" in {p.code for p in ops.ops_check()}
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(text("DELETE FROM core.etl_requests WHERE id = :i"), {"i": request_id})


def test_ops_check_key_rotation_due() -> None:
    with get_engine("migrator").begin() as conn:
        key_id, created_at = conn.execute(text(
            "SELECT id, created_at FROM core.crypto_keys "
            "WHERE purpose = 'integration_creds' AND status = 'active'")).one()
        conn.execute(text("UPDATE core.crypto_keys SET created_at = now() - interval '400 days' "
                          "WHERE id = :i"), {"i": key_id})
    try:
        due = [p for p in ops.ops_check() if p.code == "key_rotation_due"]
        assert any("integration_creds" in p.message for p in due)
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(text("UPDATE core.crypto_keys SET created_at = :c WHERE id = :i"),
                         {"c": created_at, "i": key_id})


def test_tls_expiry_warning(tmp_path: Path) -> None:
    assert ops.check_tls(_cert(tmp_path, 90), NOW) == []
    assert [p.level for p in ops.check_tls(_cert(tmp_path, 20), NOW)] == ["warning"]
    assert [p.level for p in ops.check_tls(_cert(tmp_path, 5), NOW)] == ["critical"]


MIN = timedelta(minutes=1)
SEG = 16 * 1024 * 1024


def _wal(segno: int, timeline: int = 1) -> str:
    return f"{timeline:08X}{segno // 256:08X}{segno % 256:08X}"


def _state(**kw: Any) -> ops.ArchiverState:
    base: dict[str, Any] = {
        "archive_mode": "on", "archive_timeout": 15 * MIN, "last_archived_wal": _wal(10),
        "last_archived": NOW - 2 * MIN, "last_failed": None, "current_wal": _wal(11),
        "segment_bytes": SEG, "started": NOW - timedelta(days=3), "now": NOW,
    }
    return ops.ArchiverState(**{**base, **kw})


@pytest.mark.parametrize(
    ("kw", "status", "codes"),
    [
        # oxirgi urinish xato
        ({"last_archived": NOW - 20 * MIN, "last_failed": NOW - 5 * MIN}, "alarm",
         {"wal_archiver_failed"}),
        ({"last_archived": None, "last_archived_wal": None, "last_failed": NOW - MIN},
         "alarm", {"wal_archiver_failed"}),
        # bo'sh DB: eski arxiv, lekin arxivlanmagan tugallangan segment yo'q -> ok
        ({"last_archived": NOW - timedelta(hours=5), "current_wal": _wal(11)}, "ok", set()),
        # tugallangan arxivlanmagan segmentlar RPO + grace'dan eski -> alarm
        ({"last_archived": NOW - 25 * MIN, "current_wal": _wal(13)}, "alarm",
         {"wal_archiver_lag"}),
        # grace oynasi ichida (RPO < 18 min < RPO + grace) -> ok
        ({"last_archived": NOW - 18 * MIN, "current_wal": _wal(13)}, "ok", set()),
        # statistika bo'sh (avariya/yangi start): kechikish xulosa qilinmaydi
        ({"last_archived": None, "last_archived_wal": None, "current_wal": _wal(5)},
         "ok", set()),
        # ko'p xato bo'lgan, lekin oxirgisi muvaffaqiyatli
        ({"last_failed": NOW - 60 * MIN}, "ok", set()),
        # yangi ishga tushgan server
        ({"last_archived": None, "last_archived_wal": None, "current_wal": _wal(5),
          "started": NOW - 5 * MIN}, "ok", set()),
        # replika (joriy WAL yo'q)
        ({"last_archived": NOW - timedelta(hours=5), "current_wal": None}, "ok", set()),
        # archive_timeout RPO'dan katta yoki o'chiq
        ({"archive_timeout": 30 * MIN}, "alarm", {"archive_timeout_invalid"}),
        ({"archive_timeout": timedelta(0)}, "alarm", {"archive_timeout_invalid"}),
        # arxivlash o'chiq
        ({"archive_mode": "off", "last_failed": NOW - 5 * MIN}, "skipped", set()),
    ],
)
def test_check_archiver_rules(kw: dict[str, Any], status: str, codes: set[str]) -> None:
    got_status, problems, _ = ops.check_archiver(_state(**kw))
    assert got_status == status
    assert {p.code for p in problems} == codes


def test_check_archiver_timeline_switch_is_note_not_alarm() -> None:
    st = _state(last_archived=NOW - 25 * MIN, current_wal=_wal(20, timeline=2))
    status, problems, notes = ops.check_archiver(st)
    assert (status, problems) == ("ok", [])
    assert notes and "timeline" in notes[0]


@pytest.mark.parametrize("last", ["00000003.history", "00000002.partial", "garbage"])
def test_check_archiver_non_segment_name_is_note_not_error(last: str) -> None:
    st = _state(last_archived_wal=last, last_archived=NOW - 25 * MIN, current_wal=_wal(20))
    status, problems, notes = ops.check_archiver(st)
    assert (status, problems) == ("ok", [])
    assert notes


def test_check_archiver_empty_stats_gives_note() -> None:
    st = _state(last_archived=None, last_archived_wal=None, current_wal=_wal(9))
    _, _, notes = ops.check_archiver(st)
    assert any("stats empty" in n for n in notes)


def test_ops_check_does_not_bootstrap(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom() -> None:
        raise AssertionError("bootstrap_runtime must not run for ops-check")

    monkeypatch.setattr(cli, "bootstrap_runtime", boom)
    monkeypatch.setattr(cli, "build_notifier", lambda settings: RecordingNotifier())
    cli.main(["ops-check", "--json"])
    assert '"problems"' in capsys.readouterr().out
    cli.main(["restore-test-status"])


def test_ops_check_reports_archiver_note_when_off() -> None:
    notes: list[str] = []
    ops.ops_check(notes=notes)
    with get_engine("app").connect() as conn:
        mode = conn.execute(text("SELECT current_setting('archive_mode')")).scalar_one()
    assert any("skipped" in n for n in notes) == (mode == "off")


def test_ops_check_flags_missing_next_partition() -> None:
    far = datetime.now(UTC) + timedelta(days=400)
    assert "audit_partition_missing" in {p.code for p in ops.ops_check(now=far)}


def test_ops_check_flags_stuck_running_request() -> None:
    with get_engine("migrator").begin() as conn:
        request_id = conn.execute(text(
            "INSERT INTO core.etl_requests (source, mode, requested_by, requested_at, status) "
            "VALUES ('synthetic', 'full', 0, now() - interval '12 hours', 'running') "
            "RETURNING id"
        )).scalar_one()
    try:
        assert "etl_request_stuck" in {p.code for p in ops.ops_check()}
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(text("DELETE FROM core.etl_requests WHERE id = :i"), {"i": request_id})


def test_ops_check_tls_cert_through_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "build_notifier", lambda settings: RecordingNotifier())
    # _cert() NOW (2026-09-25) ga nisbatan; haqiqiy soatga nisbatan muddati o'tgan -> critical
    assert cli.main(["ops-check", "--tls-cert", str(_cert(tmp_path, 3))]) == 1
    assert "tls_cert_expiring" in capsys.readouterr().out


def test_ops_check_unreadable_tls_cert_keeps_other_findings(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pem"
    bad.write_text("not a certificate")
    codes = {p.code for p in ops.ops_check(tls_cert=bad)}
    assert "tls_cert_unreadable" in codes


def test_cli_ops_check_keeps_collected_problems_when_later_step_raises(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "build_notifier", lambda settings: RecordingNotifier())

    def boom(**kwargs: Any) -> list[ops.Problem]:
        kwargs["collected"].append(ops.Problem("audit_partition_missing", "critical", "x"))
        raise RuntimeError("later step failed")

    monkeypatch.setattr(ops, "ops_check", boom)
    assert cli.main(["ops-check"]) == 1
    out = capsys.readouterr().out
    assert "audit_partition_missing" in out and "ops_check_error" in out


def test_cli_ops_check_reports_when_db_is_down(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    notifier = RecordingNotifier()
    monkeypatch.setattr(cli, "build_notifier", lambda settings: notifier)

    def boom(**kwargs: Any) -> list[ops.Problem]:
        raise ConnectionError("postgresql://user:secret@10.0.0.5/db unreachable")

    monkeypatch.setattr(ops, "ops_check", boom)
    assert cli.main(["ops-check", "--notify", "--extra", "db: unhealthy"]) == 1
    assert notifier.kinds == ["ops_check"]
    body = notifier.items[0].body
    assert "ops_check_error" in body
    assert "ConnectionError" in body
    assert "db: unhealthy" in body
    assert "secret" not in body
    assert "secret" not in capsys.readouterr().out


def test_cli_ops_check_json_has_notes(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["ops-check", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"problems", "notes"}


BAD_INPUTS = [
    ["--duration-seconds", "-5", "--backup", "20260925-200000F"],
    ["--duration-seconds", "9999999", "--backup", "20260925-200000F"],
    ["--duration-seconds", "10", "--backup", "evil; rm -rf"],
    ["--duration-seconds", "10", "--backup", "20260925-200000F\n"],
    ["--duration-seconds", "10", "--backup", "20260925-200000F", "--details", "a\x07b"],
    ["--duration-seconds", "10", "--backup", "20260925-200000F", "--details", "x" * 2001],
]


@pytest.mark.parametrize("args", BAD_INPUTS)
def test_cli_restore_test_record_rejects_bad_input(
    clean_restore_setting: None, args: list[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["restore-test-record", "--result", "ok", *args])
    assert exc.value.code == 2
    with get_engine("app").connect() as conn:
        assert ops.last_restore_test(conn) is None


def test_cli_restore_test_record_accepts_incremental_label_and_none(
    clean_restore_setting: None,
) -> None:
    for label in ("20260925-200000F_20260926-020000D", "none"):
        assert cli.main(["restore-test-record", "--result", "fail", "--duration-seconds", "0",
                         "--backup", label]) == 0


def test_cli_restore_test_fail_path(clean_restore_setting: None) -> None:
    assert cli.main(["restore-test-record", "--result", "fail", "--duration-seconds", "100",
                     "--backup", "20260925-200000F"]) == 0
    assert cli.main(["restore-test-status"]) == 1
    with get_engine("app").connect() as conn:
        outcome = conn.execute(text(
            "SELECT details->>'outcome', result FROM core.audit_log "
            "WHERE action = 'ops.restore_test.recorded' ORDER BY id DESC LIMIT 1")).one()
    assert tuple(outcome) == ("fail", "fail")


def test_cli_restore_test_record_and_status(
    clean_restore_setting: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["restore-test-status"]) == 1
    assert cli.main(["restore-test-record", "--result", "ok", "--duration-seconds", "1200",
                     "--backup", "20260925-200000F", "--details", "core.users 5;"]) == 0
    assert cli.main(["restore-test-status"]) == 0
    assert '"result": "ok"' in capsys.readouterr().out
    with get_engine("app").connect() as conn:
        recorded = conn.execute(text(
            "SELECT count(*) FROM core.audit_log WHERE action = 'ops.restore_test.recorded'"
        )).scalar_one()
    assert recorded >= 1


def test_cli_ops_check_notifies_only_on_problems(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    notifier = RecordingNotifier()
    monkeypatch.setattr(cli, "build_notifier", lambda settings: notifier)
    monkeypatch.setattr(ops, "ops_check", lambda **kwargs: [])
    assert cli.main(["ops-check", "--notify"]) == 0
    assert notifier.kinds == []

    stale = [ops.Problem("stale_data", "warning", "Данные витрины устарели")]
    monkeypatch.setattr(ops, "ops_check", lambda **kwargs: stale)
    assert cli.main(["ops-check", "--notify", "--extra", "backup: unhealthy"]) == 1
    assert notifier.kinds == ["ops_check"]
    assert "backup: unhealthy" in notifier.items[0].body
    assert cli.main(["ops-check", "--json"]) == 1
    assert '"code": "stale_data"' in capsys.readouterr().out


def test_cli_key_operations_are_audited(tmp_path: Path) -> None:
    before = {a: _audit_count(a) for a in ("admin.key.rotated", "admin.key.rewrapped")}
    assert cli.main(["rotate-key", "--purpose", "integration_creds"]) == 0
    new_kek = os.urandom(32)
    path = tmp_path / "kek"
    path.write_text(base64.b64encode(new_kek).decode("ascii"), encoding="ascii")
    assert cli.main(["rewrap-keys", "--new-kek-file", str(path)]) == 0
    with get_engine("migrator").begin() as conn:
        keystore.rewrap_all(conn, new_kek, get_settings().key_bytes("master_kek"))
    keystore.invalidate_keyring()
    assert _audit_count("admin.key.rotated") == before["admin.key.rotated"] + 1
    assert _audit_count("admin.key.rewrapped") == before["admin.key.rewrapped"] + 1
    with get_engine("app").connect() as conn:
        details = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.key.rewrapped' "
            "AND result = 'ok' ORDER BY id DESC LIMIT 1")).scalar_one()
    assert details["fingerprint"] == cli._kek_id(new_kek)


def test_ops_check_flags_load_users_only_in_prod() -> None:
    """M4: seed-load hisoblari (ochiq parol/TOTP) prod'da — critical; dev/test'da odatiy."""
    devtools.purge_load()  # boshqa testlar qoldirgan load_* hisoblari
    with contextlib.redirect_stdout(io.StringIO()):
        assert devtools.main(["seed-load", "--users", "2"]) == 0
    try:
        found = [p for p in ops.ops_check(env="prod") if p.code == "load_users_present"]
        assert found and found[0].level == "critical" and " 2 " in found[0].message
        assert "load_users_present" not in {p.code for p in ops.ops_check(env="test")}
    finally:
        devtools.purge_load()
    assert "load_users_present" not in {p.code for p in ops.ops_check(env="prod")}
