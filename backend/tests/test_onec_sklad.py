import json
from collections.abc import Iterator, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from app import cli, worker
from app.core import integrations
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.etl import probes
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.onec.client import OneCClient, OneCConfig, OneCError, OneCFormatError
from app.etl.onec.connector import OrgMap, stable_code
from app.etl.onec.sklad import OneCSkladConnector, periods
from app.etl.onec.sklad_models import parse_materials
from app.etl.probes import PROBES
from app.etl.runner import Runner
from app.etl.types import Mode, Window
from tests.etl_helpers import (
    TEST_AS_OF,
    RecordingNotifier,
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.helpers import clear_setting, put_setting

FIXTURES = Path(__file__).parent / "fixtures" / "onec_sklad"
BASE = "https://1c.test/con2026/hs/sklad"
ORG = OrgMap(branch_code="UGE-02", org_uid="uid-02", org_name="Чорвоқ ГЭС")


def body(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


def fake_client(payload: bytes | httpx.Response, seen: list[dict[str, Any]] | None = None,
                ) -> OneCClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append({"path": request.url.path, **json.loads(request.content)})
        return payload if isinstance(payload, httpx.Response) else httpx.Response(
            200, content=payload)

    return OneCClient(OneCConfig(BASE, "u", "p"), transport=httpx.MockTransport(handler))


def test_periods_cover_full_months() -> None:
    assert periods(Window(date(2026, 8, 10), TEST_AS_OF)) == [
        (date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), TEST_AS_OF)]


def test_current_shape_loads_account_level_stock() -> None:
    seen: list[dict[str, Any]] = []
    connector = OneCSkladConnector(fake_client(body("materials_current.json"), seen), [ORG])
    sink = CollectSink()
    stats = connector.extract(Window(date(2026, 9, 1), TEST_AS_OF), sink)
    assert seen == [{"path": "/con2026/hs/sklad/materials", "date_from": "2026-09-01",
                     "date_to": "2026-09-24", "org_uid": "uid-02"}]
    stock = [r for t, r in sink.rows if t == "fact_stock"]
    assert [(r["nom_code"], r["value"], r["qty"], r["min_qty"], r["last_move_date_id"],
             r["warehouse"], r["date_id"]) for r in stock] == [
        ("1C-ACC-1010", Decimal("450.00"), Decimal("0.000"), None, None, "Основной склад",
         20260924),
        ("1C-ACC-1050", Decimal("1250.00"), Decimal("0.000"), None, None, "Основной склад",
         20260924)]
    assert all(r["src_id"].startswith("uid-02:1C-ACC-") and r["src_id"].endswith(":202609")
               for r in stock)
    noms = {r["code"]: r for t, r in sink.rows if t == "dim_nomenclature"}
    acc = noms["1C-ACC-1050"]
    assert acc["category"] == "Запасные части" and acc["unit"] == "—"
    assert [t for t, _ in sink.rows].count("fact_stock_move") == 0
    assert set(stats.by_target) == {"fact_stock", "fact_stock_move", "dim_nomenclature"}
    assert stats.by_target["fact_stock"] == 2


def test_extended_shape_loads_nomenclature_minimum_and_moves() -> None:
    sink = CollectSink()
    OneCSkladConnector(fake_client(body("materials_extended.json")), [ORG]).extract(
        Window(date(2026, 9, 1), TEST_AS_OF), sink)
    bearing = stable_code("1C-N-", "00-00012345", "шт")
    electrodes = stable_code("1C-N-", "Электроды МР-3", "кг")
    stock = {r["nom_code"]: r for t, r in sink.rows if t == "fact_stock"}
    assert set(stock) == {bearing, electrodes}  # manfiy (сторно) qoldiq o'tkazildi
    b = stock[bearing]
    assert (b["qty"], b["min_qty"], b["value"], b["last_move_date_id"], b["warehouse"]) == (
        Decimal("2.000"), Decimal("4"), Decimal("96.00"), 20260910, "Центральный склад")
    assert stock[electrodes]["value"] == Decimal("12.35")
    moves = sorted((r["nom_code"], r["direction"], r["value"]) for t, r in sink.rows
                   if t == "fact_stock_move")
    assert moves == sorted([(bearing, "in", Decimal("48.00")),
                            (electrodes, "out", Decimal("2.00"))])
    noms = {r["code"]: r for t, r in sink.rows if t == "dim_nomenclature"}
    assert noms[bearing]["name"] == "Подшипник SKF 23140" and noms[bearing]["unit"] == "шт"


@pytest.mark.parametrize(("payload", "error"), [
    (json.dumps({"success": False, "code": "E42", "error": "нет прав"}).encode(), OneCError),
    ("\ufeff<html>Ошибка 1С</html>".encode(), OneCFormatError),
    (json.dumps({"items": []}).encode(), OneCFormatError),
    (json.dumps({"data": [{"accountName": "x", "closingSum": 1}]}).encode(), OneCFormatError),
])
def test_service_errors_are_not_retryable(payload: bytes, error: type[Exception]) -> None:
    with pytest.raises(error):
        OneCSkladConnector(fake_client(payload), [ORG]).extract(
            Window(date(2026, 9, 1), TEST_AS_OF), CollectSink())


def test_parse_accepts_numeric_account_codes() -> None:
    data = parse_materials(json.loads(body("materials_current.json")))
    assert [r.account_code for r in data.data] == ["1000", "1010", "1050", "1060"]
    assert data.data[0].is_total is True and data.data[1].closing == Decimal("450000000")


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def test_runner_clamps_window_and_replaces_vanished_accounts(source: str) -> None:
    tag = new_tag()
    run = open_run(source)
    stage(run, source, {"dim_branch": [branch_row(tag)]})
    merge_all(run, source)
    org = OrgMap(branch_code=f"T-{tag}", org_uid=f"uid-{tag}", org_name="Тест")
    full = body("materials_current.json")
    one = json.dumps({"data": [{"accountCode": "1010", "accountName": "Сырьё и материалы",
                                "isTotal": False, "openingSum": 1, "closingSum": 7000000}]})
    for payload, expected in ((full, {"1C-ACC-1010", "1C-ACC-1050"}), (one.encode(),
                                                                         {"1C-ACC-1010"})):
        connector = OneCSkladConnector(fake_client(payload), [org], months=2, source=source)
        result = Runner(connector, mode=Mode.FULL, today=TEST_AS_OF, sleep=lambda _: None).run()
        assert result.status == "success", result
        with etl_transaction() as conn:
            window_from = conn.execute(text("SELECT window_from FROM core.etl_run WHERE id = :r"),
                                       {"r": result.run_id}).scalar_one()
            codes = set(conn.execute(text(
                "SELECT n.code FROM dwh.fact_stock s JOIN dwh.dim_nomenclature n "
                "ON n.nom_id = s.nom_id WHERE s.src_system = :s AND s.date_id = 20260924"),
                {"s": source}).scalars())
        assert window_from == date(2026, 8, 1)
        assert codes == expected


@pytest.fixture
def panel() -> Iterator[None]:
    put_setting("onec.orgs", [{"branch_code": "UGE-02", "org_uid": "uid-02",
                               "org_name": "Чорвоқ ГЭС"}])
    yield
    put_setting("onec.orgs", [])
    clear_setting("onec_sklad.base_url")
    with get_engine("app").begin() as conn:
        for name in ("onec_sklad.username", "onec_sklad.password"):
            integrations.clear_secret(conn, name)


def test_make_connector_worker_and_cli(panel: None, capsys: pytest.CaptureFixture[str],
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    assert "onec_sklad" in KNOWN_SOURCES
    with pytest.raises(ConfigError, match=r"onec_sklad\.base_url"):
        make_connector("onec_sklad", get_settings())
    put_setting("onec_sklad.base_url", BASE)
    with pytest.raises(ConfigError, match="sirlari"):
        make_connector("onec_sklad", get_settings())
    with get_engine("app").begin() as conn:
        integrations.store_secret(conn, "onec_sklad.username", "u", None)
        integrations.store_secret(conn, "onec_sklad.password", "p", None)
    made = make_connector("onec_sklad", get_settings())
    assert isinstance(made, OneCSkladConnector) and made.lookback_months == 13
    assert made.orgs == [ORG]
    jobs = {j.id: j for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert {"etl_onec_sklad_full", "etl_onec_sklad_incremental"} <= set(jobs)
    # Probe: faqat soxta transport (tarmoqqa chiqmaydi).
    for payload, code in ((body("materials_current.json"), "ok"),
                          (b"<html>", "format_error"),
                          (httpx.Response(403), "auth_failed"),
                          (httpx.Response(503), "http_error")):
        monkeypatch.setattr(probes, "OneCClient", lambda *a, _p=payload, **k: fake_client(_p))
        assert PROBES["onec_sklad"]() == code
    clear_setting("onec_sklad.base_url")
    assert worker.run_onec_sklad_job(Mode.FULL, RecordingNotifier()) is None  # sozlanmagan
    assert cli.main(["onec-sklad-check"]) == 2
    assert "onec_sklad.base_url" in capsys.readouterr().out


def test_no_open_etl_transaction_during_1c_http(source: str) -> None:
    """I1: 1C so'rovlari paytida Runner'ning DB tranzaksiyasi ochiq turmasin."""
    tag = new_tag()
    run = open_run(source)
    stage(run, source, {"dim_branch": [branch_row(tag)]})
    merge_all(run, source)
    org = OrgMap(branch_code=f"T-{tag}", org_uid=f"uid-{tag}", org_name="Тест")
    payload = body("materials_current.json")
    open_tx: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        with etl_transaction() as conn:  # alohida ulanish: boshqa ugk_etl seanslari holati
            open_tx.append(int(conn.execute(text(
                "SELECT count(*) FROM pg_stat_activity WHERE usename = 'ugk_etl' "
                "AND pid <> pg_backend_pid() AND state = 'idle in transaction' "
                "AND datname = current_database()")).scalar_one()))
        return httpx.Response(200, content=payload)

    client = OneCClient(OneCConfig(BASE, "u", "p"), transport=httpx.MockTransport(handler))
    connector = OneCSkladConnector(client, [org], months=2, source=source)
    result = Runner(connector, mode=Mode.FULL, today=TEST_AS_OF, sleep=lambda _: None).run()
    assert result.status == "success", result
    assert open_tx and max(open_tx) == 0
