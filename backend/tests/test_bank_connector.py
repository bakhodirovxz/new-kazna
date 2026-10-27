import logging
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.core.config import ConfigError, get_settings
from app.core.crypto import blind_index
from app.core.db import apply_rls, new_session
from app.etl.banks.accounts import account_code
from app.etl.banks.connector import BankFileConnector
from app.etl.banks.directbank import DirectBankNotConfiguredError, OneCDirectBankClient
from app.etl.banks.registry import BankAccount
from app.etl.db import etl_transaction
from app.etl.runner import Runner, RunResult
from app.etl.types import Mode
from tests.etl_helpers import (
    FULL_WINDOW,
    TEST_AS_OF,
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)

HEAD = "row_type;account;date;doc_id;direction;amount;counterparty_inn;counterparty_name;item_code"
ORDERS = ("doc_id;account;date;status;status_date;amount;counterparty_inn;"
          "counterparty_name;item_code")


def new_account(prefix: str = "2021000090") -> str:
    return prefix + f"{uuid.uuid4().int % 10**10:010d}"


class CollectSink:
    """ReportingSink: staging qatorlari va xatolarni xotirada yig'adi."""

    def __init__(self, load_id: int) -> None:
        self.load_id = load_id
        self.rows: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[dict[str, Any]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None:
        self.errors.append({"target": target, "code": code, "message": message, "src_id": src_id})

    def facts(self) -> list[dict[str, Any]]:
        return [row for target, row in self.rows if target.startswith("fact_")]


class PlainSink:
    def add(self, target: str, row: Mapping[str, Any]) -> None:
        raise AssertionError("chaqirilmasligi kerak")


@dataclass
class Env:
    source: str
    branch_code: str
    branch_id: int
    uzs: str  # ochiq hisob raqamlari faqat test ichida
    fx: str
    accounts: list[BankAccount]
    inbox: Path
    archive: Path

    def connector(self, **kw: Any) -> BankFileConnector:
        return BankFileConnector(self.inbox, self.archive, self.accounts, source=self.source,
                                 min_age=0, **kw)

    def run(self) -> RunResult:
        return Runner(self.connector(), mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                      sleep=lambda _: None).run()

    def write(self, bank: str, name: str, lines: list[str]) -> Path:
        path = self.inbox / bank / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def code(self, account: str) -> str:
        return account_code(account)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    source = new_source()
    branch = branch_row(new_tag())
    run = open_run(source)
    stage(run, source, {"dim_branch": [branch],
                        "fx_rate": [{"currency": "XTL", "date_id": 20260920, "rate": 12000}]})
    merge_all(run, source)
    with etl_transaction() as conn:
        branch_id = int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": branch["code"]}).scalar_one())
    uzs, fx = new_account(), new_account("2020888090")
    accounts = [
        BankAccount(code=account_code(uzs), bank_code="sqb", branch_code=branch["code"],
                    currency="UZS", gl_account="5110", last4=uzs[-4:]),
        BankAccount(code=account_code(fx), bank_code="nbu", branch_code=branch["code"],
                    currency="XTL", gl_account="5210", last4=fx[-4:]),
    ]
    inbox, archive = tmp_path / "inbox", tmp_path / "archive"
    for folder in (inbox / "sqb", inbox / "nbu", archive):
        folder.mkdir(parents=True)
    yield Env(source, branch["code"], branch_id, uzs, fx, accounts, inbox, archive)
    purge_source(source)


def statement(account: str, day: str = "2026-09-22") -> list[str]:
    return [
        HEAD,
        f"OB;{account};{day};;;1000000000.00;;;",
        f"L;{account};{day};D-1;in;250000000.00;301234567;ООО «Покупатель»;PKM54-I06",
        f"L;{account};{day};D-2;out;50000000.50;;Иванов Иван;",
        f"CB;{account};{day};;;1199999999.50;;;",
    ]


def _errors(run_id: int) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(
            "SELECT code, src_id, message FROM core.etl_error WHERE run_id = :r "
            "AND step = 'extract' ORDER BY id"), {"r": run_id}).mappings().all()]


def test_runner_loads_statement_orders_and_publishes(env: Env) -> None:
    env.write("sqb", "vypiska_0922.csv", statement(env.uzs))
    env.write("nbu", "fx_0922.csv", [HEAD, f"OB;{env.fx};2026-09-22;;;1010.00;;;",
                                     f"L;{env.fx};2026-09-22;F-1;out;10.00;;;",
                                     f"CB;{env.fx};2026-09-22;;;1000.00;;;"])
    env.write("sqb", "orders_0922.csv", [
        ORDERS, f"P-1;{env.uzs};2026-09-22;executed;2026-09-22;50000000.50;;;PKM54-O09",
        f"P-2;{env.uzs};2026-09-23;rejected;2026-09-23;7000000.00;301234567;ООО «Покупатель»;"])
    result = env.run()
    assert result.status == "success", result
    uzs, fx = env.code(env.uzs), env.code(env.fx)
    with etl_transaction() as conn:
        balances = {r.code: float(r.balance) for r in conn.execute(text(
            "SELECT b.code, f.balance FROM dwh.fact_balance f JOIN dwh.dim_bank b "
            "ON b.bank_id = f.bank_id WHERE f.src_system = :s"), {"s": env.source})}
        cash = {r.src_id: (r.direction, float(r.amount), r.gl_account, r.has_cp) for r in
                conn.execute(text(
                    "SELECT src_id, direction, amount, gl_account, cp_id IS NOT NULL AS has_cp "
                    "FROM dwh.fact_cashflow WHERE src_system = :s"), {"s": env.source})}
        orders = {r.src_id: (r.status, float(r.amount), r.status_date_id) for r in conn.execute(
            text("SELECT src_id, status, amount, status_date_id FROM dwh.fact_payment_order "
                 "WHERE src_system = :s"), {"s": env.source})}
        bank = conn.execute(text("SELECT bank_name, account_enc IS NOT NULL AS enc, account_bidx "
                                 "FROM dwh.dim_bank WHERE code = :c"), {"c": uzs}).one()
        ledger = conn.execute(text("SELECT kind, status, row_count FROM core.bank_files "
                                   "WHERE run_id = :r ORDER BY kind, row_count"),
                              {"r": result.run_id}).all()
    assert balances == {uzs: 1200.0, fx: 12.0}  # 1000 XTL × 12000 = 12 mln so'm
    assert cash == {f"{uzs}:D-1": ("in", 250.0, "5110", True),
                    f"{uzs}:D-2": ("out", 50.0, "5110", False),  # jismoniy shaxs — kontragentsiz
                    f"{fx}:F-1": ("out", 0.12, "5210", False)}
    assert orders == {f"{uzs}:P-1": ("исполнено", 50.0, 20260922),
                      f"{uzs}:P-2": ("отклонено", 7.0, 20260923)}
    key = get_settings().key_bytes("blind_index_key")
    assert (bank.bank_name, bank.enc) == ("Узпромстройбанк", True)
    assert bytes(bank.account_bidx) == blind_index(key, "account", env.uzs)
    assert [tuple(r) for r in ledger] == [("orders", "staged", 2), ("statement", "staged", 2),
                                          ("statement", "staged", 3)]
    archived = sorted(p.name for p in env.archive.rglob("*.csv"))
    assert len(archived) == 3 and all(len(n) == len("0" * 64 + ".csv") for n in archived)
    with new_session() as s:
        apply_rls(s, None)
        closing = dict(s.execute(text(
            "SELECT bank_name, closing_balance FROM pub.agg_cash_bank_month "
            "WHERE branch_id = :b AND month_id = 202609"), {"b": env.branch_id}).all())
    assert {k: float(v) for k, v in closing.items()} == {"Узпромстройбанк": 1200.0,
                                                         "Национальный банк": 12.0}


def test_redelivery_is_idempotent_and_second_file_keeps_first(env: Env) -> None:
    first = env.write("sqb", "a.csv", statement(env.uzs))
    assert env.run().status == "success"
    (env.inbox / "sqb" / "a_copy.csv").write_bytes(first.read_bytes())  # qayta yetkazish
    env.write("sqb", "b.csv", [HEAD, f"L;{env.uzs};2026-09-23;D-3;out;1000000.00;;;"])
    result = env.run()
    assert result.status == "success", result
    uzs = env.code(env.uzs)
    with etl_transaction() as conn:
        ids = sorted(conn.execute(text("SELECT src_id FROM dwh.fact_cashflow "
                                       "WHERE src_system = :s"), {"s": env.source}).scalars())
        staged = conn.execute(text("SELECT count(*) FROM core.bank_files WHERE run_id = :r"),
                              {"r": result.run_id}).scalar_one()
    assert ids == sorted([f"{uzs}:D-1", f"{uzs}:D-2", f"{uzs}:D-3"])
    assert staged == 1  # faqat b.csv; a_copy.csv — o'sha SHA-256, qayta o'qilmadi


def test_failed_run_files_are_reprocessed(env: Env) -> None:
    env.write("sqb", "a.csv", statement(env.uzs))
    first = CollectSink(open_run(env.source))
    env.connector().extract(FULL_WINDOW, first)
    assert len(first.facts()) == 3
    with etl_transaction() as conn:
        conn.execute(text("UPDATE core.etl_run SET status = 'failed' WHERE id = :r"),
                     {"r": first.load_id})
    second = CollectSink(open_run(env.source))
    env.connector().extract(FULL_WINDOW, second)
    assert len(second.facts()) == 3
    with etl_transaction() as conn:
        conn.execute(text("UPDATE core.etl_run SET status = 'success' WHERE id = :r"),
                     {"r": second.load_id})
    third = CollectSink(open_run(env.source))
    env.connector().extract(FULL_WINDOW, third)
    assert third.rows == []


def test_malformed_rows_are_reported_and_valid_rows_loaded(env: Env) -> None:
    other = new_account()
    env.write("sqb", "mixed.csv", [
        HEAD,
        f"L;{env.uzs};2026-09-22;D-1;in;10.00;;;",       # 2 — to'g'ri
        f"L;{env.uzs};2026-09-22;D-2;in;1 000.00;;;",    # 3 — bad_row
        f"L;{other};2026-09-22;D-3;in;10.00;;;",         # 4 — unknown_account
        f"L;{env.uzs};2026-09-22;D-1;in;10.00;;;",       # 5 — duplicate_doc
        f"OB;{env.uzs};2026-09-21;;;100.00;;;",          # 6
        f"L;{env.uzs};2026-09-21;D-4;out;10.00;;;",      # 7
        f"CB;{env.uzs};2026-09-21;;;95.00;;;",           # 8 — statement_mismatch (90 kutilgan)
    ])
    env.write("sqb", "wrong_bank.csv", [HEAD, f"CB;{env.fx};2026-09-22;;;5.00;;;"])
    env.write("nbu", "fx_old.csv", [HEAD, f"CB;{env.fx};2026-01-05;;;5.00;;;"])
    result = env.run()
    assert result.status == "success", result
    errors = _errors(result.run_id or 0)
    assert sorted(e["code"] for e in errors) == ["bad_row", "duplicate_doc", "fx_rate_missing",
                                                 "statement_mismatch", "unknown_account",
                                                 "wrong_bank"]
    assert any(e["src_id"] == "sqb/mixed.csv:3" for e in errors)
    with etl_transaction() as conn:
        ids = set(conn.execute(text("SELECT src_id FROM dwh.fact_cashflow WHERE src_system = :s"),
                               {"s": env.source}).scalars())
    assert ids == {f"{env.code(env.uzs)}:D-1"}  # D-4 — nomuvofiq ko'chirma, yuklanmaydi


def test_file_level_rejection_is_final(env: Env) -> None:
    (env.inbox / "sqb" / "cp1251.csv").write_bytes(
        f"{HEAD}\nL;{env.uzs};2026-09-22;D-1;in;1.00;;Тест;\n".encode("cp1251"))
    first = env.run()
    assert [e["code"] for e in _errors(first.run_id or 0)] == ["bad_encoding"]
    with etl_transaction() as conn:
        status = conn.execute(text("SELECT status FROM core.bank_files WHERE run_id = :r"),
                              {"r": first.run_id}).scalar_one()
    assert status == "rejected"
    second = env.run()
    assert _errors(second.run_id or 0) == []


def test_account_number_never_leaks(env: Env, caplog: pytest.LogCaptureFixture,
                                    capsys: pytest.CaptureFixture[str]) -> None:
    caplog.set_level(logging.DEBUG)
    env.write("sqb", f"vypiska_{env.uzs}_0922.csv",
              [*statement(env.uzs), f"L;{env.uzs};2026-09-22;D-9;in;1 0;;;"])
    env.write("sqb", f"unknown_{env.uzs}.csv",
              [HEAD, f"L;{new_account()};2026-09-22;X-1;in;1.00;;;"])
    result = env.run()
    with etl_transaction() as conn:
        messages = " ".join(conn.execute(text(
            "SELECT coalesce(src_id, '') || ' ' || message FROM core.etl_error "
            "WHERE run_id = :r"), {"r": result.run_id}).scalars())
        ledger = " ".join(conn.execute(text(
            "SELECT file_name || ' ' || coalesce(archive_path, '') FROM core.bank_files "
            "WHERE run_id = :r"), {"r": result.run_id}).scalars())
    archived = " ".join(str(p) for p in env.archive.rglob("*"))
    out = capsys.readouterr()
    for place in (messages, ledger, archived, caplog.text, out.out, out.err):
        assert env.uzs not in place
    assert f"…{env.uzs[-4:]}" in ledger


def test_fresh_and_non_csv_files_are_ignored(env: Env) -> None:
    path = env.write("sqb", "fresh.csv", statement(env.uzs))
    (env.inbox / "sqb" / "upload.tmp").write_text("x", encoding="utf-8")
    moment = path.stat().st_mtime + 10
    sink = CollectSink(open_run(env.source))
    BankFileConnector(env.inbox, env.archive, env.accounts, source=env.source, min_age=60,
                      now=lambda: moment).extract(FULL_WINDOW, sink)
    assert sink.rows == [] and not list(env.archive.rglob("*.csv"))


def test_extract_requires_reporting_sink(env: Env) -> None:
    with pytest.raises(TypeError, match="ReportingSink"):
        env.connector().extract(FULL_WINDOW, PlainSink())


def test_healthcheck(env: Env, tmp_path: Path) -> None:
    assert env.connector().healthcheck().ok is True
    missing = BankFileConnector(tmp_path / "nope", env.archive, env.accounts)
    assert missing.healthcheck().ok is False


def test_directbank_stub_is_not_configured() -> None:
    with pytest.raises(DirectBankNotConfiguredError, match="DirectBank") as exc:
        OneCDirectBankClient()
    assert isinstance(exc.value, ConfigError)
