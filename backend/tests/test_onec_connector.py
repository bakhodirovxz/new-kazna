import json
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from app import cli
from app.core import integrations
from app.core.config import ConfigError
from app.core.db import get_engine
from app.dwh import builds
from app.dwh.reference import current_setting
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.onec.client import OneCClient, OneCConfig, OneCFormatError, OneCTruncatedError
from app.etl.onec.connector import (
    SOURCE,
    OneCConnector,
    OrgMap,
    stable_code,
    to_mln,
    unmapped_branch,
)
from app.etl.probes import PROBES
from app.etl.runner import Runner
from app.etl.types import Mode, Window
from tests.etl_helpers import TEST_AS_OF, purge_source
from tests.helpers import clear_setting, put_setting

FIXTURES = Path(__file__).parent / "fixtures" / "onec"
BASE = "https://1c.test/con2026/hs/aiassistant"
CFG = OneCConfig(BASE, "u", "p", 64 * 1024 * 1024, "", False)
ORGS = [OrgMap("UGE-02", "uid-02", "Чарвакская ГЭС")]
WINDOW = Window(date(2026, 8, 1), TEST_AS_OF)
MAT = stable_code("1C-O-", "Материал харажатлар (тоза)")
KOM = stable_code("1C-O-", "Коммунал хизматлар")


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))

    def of(self, target: str) -> list[dict[str, Any]]:
        return [row for t, row in self.rows if t == target]


def fake_1c(overrides: dict[str, httpx.Response] | None = None,
            log: list[tuple[str, Any]] | None = None,
            on_request: Any = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if on_request is not None:
            on_request()
        path = request.url.path.removeprefix("/con2026/hs/aiassistant")
        body = json.loads(request.content)
        if log is not None:
            log.append((path, body))
        if overrides and path in overrides:
            return overrides[path]
        if path == "/payments":
            if body.get("limit") == 1:
                return httpx.Response(200, content=b'{"payments": []}')
            return httpx.Response(200, content=(FIXTURES / "payments_uge02.json").read_bytes())
        if path == "/budget":
            name = "budget_plan_2026.json" if body["Year"] == 2026 else None
            content = (FIXTURES / name).read_bytes() if name else b'{"items": []}'
            return httpx.Response(200, content=content)
        if path == "/income":
            return httpx.Response(200, content=(FIXTURES / "income.json").read_bytes())
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def connector(transport: httpx.MockTransport, **kw: Any) -> OneCConnector:
    client = OneCClient(CFG, transport=transport)
    return OneCConnector(client, ORGS, now=lambda: datetime(2026, 9, 24, 21, 0, tzinfo=UTC), **kw)


def test_helpers() -> None:
    assert stable_code("1C-O-", "Материал  харажатлар (ТОЗА) ") == MAT
    assert MAT.startswith("1C-O-") and len(MAT) == 17
    assert to_mln(Decimal("2500000.50")) == Decimal("2.50")
    assert to_mln(Decimal("125000000")) == Decimal("125.00")
    assert unmapped_branch("ООО Foo") == "1C:ООО Foo"
    assert "onec" in KNOWN_SOURCES


def test_extract_maps_payments_and_plan() -> None:
    log: list[tuple[str, Any]] = []
    sink = CollectSink()
    stats = connector(fake_1c(log=log)).extract(WINDOW, sink)
    assert ("/payments", {"org_uid": "uid-02", "date_from": "20260801", "date_to": "20260924",
                          "limit": 100000}) in log
    assert ("/budget", {"Year": 2026, "Mode": "plan"}) in log
    assert not any(path == "/income" for path, _ in log)  # income standart bo'yicha o'chiq
    cash = sink.of("fact_cashflow")
    got = [(r["src_id"], r["date_id"], r["amount"], r["item_code"], r["direction"])
           for r in cash]
    assert got == [("uid-02:000101:2026-08-05", 20260805, Decimal("125.00"), MAT, "out"),
            ("uid-02:000102:2026-08-06", 20260806, Decimal("2.50"), KOM, "out")]
    assert all(r["branch_code"] == "UGE-02" and r["doc_type"] == "onec_payment" for r in cash)
    plan = sorted(sink.of("fact_payment_plan"), key=lambda r: r["date_id"])
    assert [(r["date_id"], r["item_code"], r["amount"]) for r in plan] == [
        (20260801, MAT, Decimal("200.00")), (20261201, KOM, Decimal("3.00"))]
    items = {r["code"]: r for r in sink.of("dim_item")}
    assert set(items) == {MAT, KOM} and items[MAT]["direction"] == "out"
    assert items[MAT]["activity"] == "operating"
    # 000103 (0) va 000104 (manfiy) o'tkazib yuboriladi — ularning kontragenti "X" ham yaratilmaydi.
    cps = {r["name"] for r in sink.of("dim_counterparty")}
    assert cps == {"ООО «Гидромонтаж»", "=cmd|' /C calc'!A0"}
    assert stats.by_target["fact_cashflow"] == 2 and "fact_payment_plan" in stats.by_target
    assert connector(fake_1c()).control_totals(WINDOW) is None


def test_income_when_enabled_gets_distinct_ids() -> None:
    sink = CollectSink()
    connector(fake_1c(), income_enabled=True).extract(WINDOW, sink)
    income = [r for r in sink.of("fact_cashflow") if r["direction"] == "in"]
    assert len({r["src_id"] for r in income}) == 2
    assert all(r["amount"] == Decimal("900.00") and r["branch_code"] == "UGE-02" for r in income)
    assert income[0]["item_code"] == stable_code("1C-I-", "Реализация электроэнергии")


def test_payments_at_limit_raise_truncated() -> None:
    rows = [{"number": str(n), "date": "2026-08-05", "sum": 1000000, "contractor_name": "A",
             "contract_number": "1", "expense_type_name": "B"} for n in range(1000)]
    transport = fake_1c({"/payments": httpx.Response(200, json={"payments": rows})})
    with pytest.raises(OneCTruncatedError):
        connector(transport, page_limit=1000).extract(WINDOW, CollectSink())


def test_bad_structure_is_format_error() -> None:
    for body in ({"payments": [{"number": "1", "date": "05.08.2026", "sum": 1,
                                "expense_type_name": "B"}]},
                 {"data": []},
                 {"payments": [{"number": "1", "date": "2026-08-05", "sum": "1 000",
                                "expense_type_name": "B"}]}):
        transport = fake_1c({"/payments": httpx.Response(200, json=body)})
        with pytest.raises(OneCFormatError):
            connector(transport).extract(WINDOW, CollectSink())


def test_healthcheck() -> None:
    assert connector(fake_1c()).healthcheck().ok is True
    down = connector(fake_1c({"/payments": httpx.Response(503)})).healthcheck()
    assert down.ok is False and "503" in down.detail
    assert connector(fake_1c()).watermark().value == datetime(2026, 9, 24, 21, 0, tzinfo=UTC)


@pytest.fixture
def onec_source() -> Iterator[None]:
    yield
    purge_source(SOURCE)


def _run(transport: httpx.MockTransport, orgs: list[OrgMap] | None = None) -> Any:
    client = OneCClient(CFG, transport=transport)
    return Runner(OneCConnector(client, orgs or ORGS), mode=Mode.FULL, today=TEST_AS_OF,
                  sleep=lambda _: None).run()


def test_runner_loads_and_publishes(onec_source: None) -> None:
    result = _run(fake_1c())
    assert result.status == "success", result
    with etl_transaction() as conn:
        amounts = conn.execute(text(
            "SELECT sum(amount) FROM dwh.fact_cashflow WHERE src_system = 'onec'")).scalar_one()
        assert builds.active_build(conn) == result.build_id
    assert amounts == Decimal("127.50")


def test_runner_fails_without_publish_on_bad_payload(onec_source: None) -> None:
    with etl_transaction() as conn:
        before = builds.active_build(conn)
    html = httpx.Response(200, text="<html>Ошибка</html>")
    result = _run(fake_1c({"/payments": html}))
    assert result.status == "failed" and "OneCFormatError" in (result.error or "")
    with etl_transaction() as conn:
        assert builds.active_build(conn) == before


def test_unmapped_org_blocks_publish(onec_source: None) -> None:
    plan = {"items": [{"org_name": "Неизвестная организация",
                       "expense_type_name": "B", "month": 8, "plan_sum": 1000000}]}
    result = _run(fake_1c({"/budget": httpx.Response(200, json=plan)}))
    assert result.status == "failed_quality"
    with etl_transaction() as conn:
        messages = conn.execute(text(
            "SELECT message FROM core.etl_error WHERE run_id = :r AND code = 'missing_branch'"),
            {"r": result.run_id}).scalars().all()
    assert messages and all("1C:Неизвестная организация" in m for m in messages)


def test_no_db_transaction_is_open_while_waiting_on_1c(onec_source: None,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    """M9: 1C javobini kutayotganda etl tranzaksiyasi ochiq turmasligi kerak."""
    from contextlib import contextmanager

    from app.etl import runner as runner_module

    open_now = [0]
    seen_open: list[int] = []
    real = runner_module.etl_transaction

    @contextmanager
    def counting() -> Iterator[Any]:
        with real() as conn:
            open_now[0] += 1
            try:
                yield conn
            finally:
                open_now[0] -= 1

    monkeypatch.setattr(runner_module, "etl_transaction", counting)
    result = _run(fake_1c(on_request=lambda: seen_open.append(open_now[0])))
    assert result.status == "success", result
    assert seen_open and set(seen_open) == {0}


@pytest.fixture
def onec_panel() -> Iterator[None]:
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.integration_credentials WHERE name LIKE 'onec.%'"))
    for key in ("onec.base_url", "onec.max_mb", "onec.orgs", "onec.income_enabled"):
        clear_setting(key)


def _configure_panel() -> None:
    put_setting("onec.base_url", BASE)
    with get_engine("app").begin() as conn:
        integrations.store_secret(conn, "onec.username", "api-user", None)
        integrations.store_secret(conn, "onec.password", "s3cr3t-pass", None)


def test_cli_onec_orgs_and_make_connector(tmp_path: Path, onec_panel: None,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(ConfigError, match="не настроена"):
        make_connector("onec")
    _configure_panel()
    with pytest.raises(ConfigError, match=r"onec\.orgs"):
        make_connector("onec")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"branch_code": "NOPE", "org_uid": "u1", "org_name": "A"}]),
                   encoding="utf-8")
    assert cli.main(["onec-orgs", "--file", str(bad)]) == 1
    good = tmp_path / "orgs.json"
    good.write_text(json.dumps([{"branch_code": "UGE-02", "org_uid": "uid-02",
                                 "org_name": "Чарвакская ГЭС"}], ensure_ascii=False),
                    encoding="utf-8")
    assert cli.main(["onec-orgs", "--file", str(good)]) == 0
    with get_engine("app").connect() as conn:
        assert current_setting(conn, "onec.orgs")[0]["org_uid"] == "uid-02"
    with get_engine("migrator").connect() as conn:
        details = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.setting.updated' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert details["via"] == "cli" and details["orgs"] == 1
    assert cli.main(["onec-orgs"]) == 0 and "uid-02" in capsys.readouterr().out
    made = make_connector("onec")
    assert isinstance(made, OneCConnector) and made.orgs == [OrgMap("UGE-02", "uid-02",
                                                                    "Чарвакская ГЭС")]
    assert made.income_enabled is False  # sukut bo'yicha o'chiq


def test_check_cli_and_job_skip_when_not_configured(onec_panel: None,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    from app import worker
    from app.etl.types import Mode
    from tests.etl_helpers import RecordingNotifier

    with etl_transaction() as conn:
        before = conn.execute(text("SELECT count(*) FROM core.etl_run WHERE source = 'onec'")
                              ).scalar_one()
    assert cli.main(["onec-check"]) == 2
    assert "не настроена" in capsys.readouterr().out
    assert worker.run_etl_job("onec", Mode.FULL, RecordingNotifier()) is None
    with etl_transaction() as conn:
        runs = conn.execute(text("SELECT count(*) FROM core.etl_run WHERE source = 'onec'")
                            ).scalar_one()
    assert runs == before


def test_probe_codes(onec_panel: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.etl.onec import probe as probe_module

    assert PROBES["onec"]() == "not_configured"
    _configure_panel()

    def run(response: httpx.Response | Exception) -> str:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/payments")
            assert json.loads(request.content)["limit"] == 1
            if isinstance(response, Exception):
                raise response
            return response

        monkeypatch.setattr(probe_module, "_TRANSPORT", httpx.MockTransport(handler))
        return PROBES["onec"]()

    assert run(httpx.Response(200, json={"payments": []})) == "ok"
    assert run(httpx.Response(401)) == "auth_failed"
    assert run(httpx.Response(403)) == "auth_failed"
    assert run(httpx.Response(404)) == "http_error"
    assert run(httpx.Response(200, text="<html>")) == "format_error"
    assert run(httpx.Response(200, json={"data": []})) == "format_error"
    assert run(httpx.Response(503)) == "http_error"
    assert run(httpx.ReadTimeout("slow")) == "timeout"
    assert run(httpx.ConnectError("refused")) == "connect_failed"
    assert run(httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] s3cr3t")) == "tls_failed"
