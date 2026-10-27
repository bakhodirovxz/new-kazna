import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text

from app import cli, worker
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.dwh.reference import current_setting
from app.etl.banks.accounts import account_code
from app.etl.banks.connector import BankFileConnector
from app.etl.banks.ledger import DbFileLedger, FileEntry
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.staging import DbStagingSink
from tests.etl_helpers import RecordingNotifier, new_source, open_run
from tests.helpers import put_setting

HEADER = "account;bank_code;branch_code;currency;gl_account"
ACC = "20210000900100000077"


@pytest.fixture
def accounts_setting() -> Iterator[None]:
    yield
    put_setting("banks.accounts", [])


def test_bank_accounts_cli(tmp_path: Path, accounts_setting: None,
                           capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "accounts.csv"
    good.write_text(f"{HEADER}\n{ACC[:4]} {ACC[4:]};sqb;UGE-02;uzs;5110\n", encoding="utf-8")
    assert cli.main(["bank-accounts", "--file", str(good)]) == 0
    with get_engine("app").connect() as conn:
        stored = current_setting(conn, "banks.accounts")
    assert stored == [{"code": account_code(ACC), "bank_code": "sqb", "branch_code": "UGE-02",
                       "currency": "UZS", "gl_account": "5110", "last4": "0077"}]
    assert ACC not in json.dumps(stored)
    with get_engine("migrator").connect() as conn:
        details = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.setting.updated' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert details["via"] == "cli" and details["accounts"] == 1
    assert cli.main(["bank-accounts"]) == 0
    bad = tmp_path / "bad.csv"
    bad.write_text(f"{HEADER}\n{ACC};sqb;NOPE;UZS;5110\n", encoding="utf-8")
    assert cli.main(["bank-accounts", "--file", str(bad)]) == 1
    short = tmp_path / "short.csv"
    short.write_text(f"{HEADER}\n{ACC[:-1]};sqb;UGE-02;UZS;5110\n", encoding="utf-8")
    assert cli.main(["bank-accounts", "--file", str(short)]) == 1
    out = capsys.readouterr().out
    assert "…0077" in out and "NOPE" in out
    assert ACC not in out and ACC[:-1] not in out


def test_make_connector_banks_and_directbank(tmp_path: Path, accounts_setting: None) -> None:
    settings = get_settings().model_copy(update={"bank_inbox_dir": str(tmp_path / "in"),
                                                 "bank_archive_dir": str(tmp_path / "ar")})
    assert {"banks", "directbank"} <= set(KNOWN_SOURCES)
    with pytest.raises(ConfigError, match=r"banks\.accounts"):
        make_connector("banks", settings)
    put_setting("banks.accounts", [{"code": "BA-0123456789abcdef", "bank_code": "sqb",
                                    "branch_code": "UGE-02", "currency": "UZS",
                                    "gl_account": "5110", "last4": "0001"}])
    made = make_connector("banks", settings)
    assert isinstance(made, BankFileConnector) and made.inbox == tmp_path / "in"
    assert made.accounts[0].code == "BA-0123456789abcdef" and made.formats["sqb"] == "canonical"
    with pytest.raises(ConfigError, match="DirectBank"):
        make_connector("directbank", settings)


def test_bank_files_cli(capsys: pytest.CaptureFixture[str]) -> None:
    DbFileLedger().mark(FileEntry(uuid.uuid4().hex * 2, "sqb", "sqb/…0001_x.csv", 10, "unknown",
                                  "rejected", None, 0, 1, None))
    assert cli.main(["bank-files", "--limit", "5"]) == 0
    assert "sqb/…0001_x.csv" in capsys.readouterr().out


def test_notify_bank_errors() -> None:
    source = new_source()
    run = open_run(source)
    notifier = RecordingNotifier()
    assert worker.notify_bank_errors(run, notifier) == 0 and notifier.items == []
    with etl_transaction() as conn:
        sink = DbStagingSink(conn, run, source)
        for code in ("bad_row", "bad_row", "unknown_account"):
            sink.error(target="bank_file", code=code, message="m")
    assert worker.notify_bank_errors(run, notifier) == 3
    assert notifier.kinds == ["bank_rows_rejected"]
    assert "bad_row: 2" in notifier.items[0].body
    assert "unknown_account: 1" in notifier.items[0].body


def test_banks_job_skips_when_not_configured(accounts_setting: None,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(worker, "run_etl_job", lambda source, mode, notifier: calls.append(source))
    assert worker.run_banks_job(RecordingNotifier()) is None and calls == []
    jobs = {j.id: j for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert jobs["etl_banks"].func is worker.run_banks_job
