import json
from collections.abc import Callable, Iterator, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from app import cli, worker
from app.core.config import ConfigError, get_settings
from app.etl.cbu.client import CbuClient, CbuError
from app.etl.cbu.connector import CbuRatesConnector
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.runner import Runner
from app.etl.types import ConnectorUnavailableError, Mode, Window
from tests.etl_helpers import TEST_AS_OF, RecordingNotifier, new_source, purge_source

FIXTURES = Path(__file__).parent / "fixtures" / "cbu"
WINDOW = Window(date(2026, 9, 1), TEST_AS_OF)


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


def fake_cbu(bodies: Mapping[str, bytes | httpx.Response],
             seen: list[httpx.Request] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        day = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        body = bodies.get(day)
        if isinstance(body, httpx.Response):
            return body
        return httpx.Response(200, content=body if body is not None else b"[]")

    return httpx.MockTransport(handler)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def client(bodies: Mapping[str, bytes | httpx.Response], **kw: Any) -> CbuClient:
    return CbuClient(transport=fake_cbu(bodies), **kw)


def test_parse_fixture_and_request_shape() -> None:
    seen: list[httpx.Request] = []
    c = CbuClient(transport=fake_cbu({"2026-09-24": fixture("all_2026-09-24.json")}, seen))
    rates = {r.ccy: r for r in c.rates(date(2026, 9, 24))}
    assert seen[0].url.path == "/ru/arkhiv-kursov-valyut/json/all/2026-09-24/"
    assert seen[0].method == "GET"
    assert rates["USD"].per_unit == Decimal("11814.050000")
    assert rates["USD"].day == date(2026, 9, 24)
    assert rates["IDR"].nominal == 10 and rates["IDR"].per_unit == Decimal("0.666000")
    assert c.http.trust_env is False and c.http.follow_redirects is False


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="<html>Технические работы</html>"),
    httpx.Response(200, json={"rates": []}),
    httpx.Response(200, json=[{"Ccy": "USD", "Rate": "11 814,05", "Nominal": "1",
                               "Date": "24.09.2026"}]),
    httpx.Response(200, json=[{"Ccy": "USD", "Rate": "11814.05", "Nominal": "0",
                               "Date": "24.09.2026"}]),
    httpx.Response(302, headers={"location": "https://evil.test/"}),
    httpx.Response(404),
])
def test_bad_responses_are_not_retryable(response: httpx.Response) -> None:
    with pytest.raises(CbuError) as exc:
        client({"2026-09-24": response}).rates(date(2026, 9, 24))
    assert not isinstance(exc.value, ConnectorUnavailableError)


def test_transient_errors_are_retryable() -> None:
    with pytest.raises(ConnectorUnavailableError, match="503"):
        client({"2026-09-24": httpx.Response(503)}).rates(date(2026, 9, 24))

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(ConnectorUnavailableError, match="тайм-аут"):
        CbuClient(transport=httpx.MockTransport(timeout)).rates(date(2026, 9, 24))


def test_size_cap() -> None:
    big = httpx.Response(200, content=b"[" + b" " * 2000 + b"]")
    with pytest.raises(CbuError, match="больше"):
        client({"2026-09-24": big}, max_bytes=1000).rates(date(2026, 9, 24))


def test_connector_extract_dates_and_units() -> None:
    sleeps: list[float] = []
    connector = CbuRatesConnector(
        client({"2026-09-24": fixture("all_2026-09-24.json"),
                "2026-09-01": fixture("all_2026-09-01.json")}),
        ["USD", "EUR", "IDR"], date_from=date(2026, 9, 1), date_to=date(2026, 9, 2),
        sleep=sleeps.append)
    assert connector.dates() == [date(2026, 9, 1), date(2026, 9, 2)]
    sink = CollectSink()
    stats = connector.extract(WINDOW, sink)
    # 1-sentabr — 28-avgust kursi shu kun uchun saqlanadi; 2-sentabr — bo'sh javob (o'tkaziladi).
    assert [row for _, row in sink.rows] == [
        {"currency": "USD", "date_id": 20260901, "rate": Decimal("11801.230000")}]
    assert stats.rows == 1 and stats.by_target == {"fx_rate": 1} and sleeps == [0.2]


def test_default_dates_are_last_days() -> None:
    connector = CbuRatesConnector(client({}), ["USD"], days=3, today=lambda: date(2026, 9, 24))
    assert connector.dates() == [date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24)]
    with pytest.raises(ValueError):
        CbuRatesConnector(client({}), ["USD"], date_from=date(2026, 9, 2), date_to=date(2026, 9, 1))
    with pytest.raises(ValueError):
        CbuRatesConnector(client({}), ["USD"], date_from=date(2024, 1, 1),
                          date_to=date(2026, 9, 24))


def test_rate_dated_after_request_is_error() -> None:
    body = json.dumps([{"Ccy": "USD", "Rate": "1.00", "Nominal": "1", "Date": "25.09.2026"}])
    connector = CbuRatesConnector(client({"2026-09-24": body.encode()}), ["USD"], days=1,
                                  today=lambda: date(2026, 9, 24))
    with pytest.raises(CbuError, match="позже"):
        connector.extract(WINDOW, CollectSink())


def test_healthcheck() -> None:
    ok = CbuRatesConnector(client({"2026-09-24": fixture("all_2026-09-24.json")}), ["USD"],
                           today=lambda: date(2026, 9, 24))
    assert ok.healthcheck().ok is True
    down = CbuRatesConnector(client({"2026-09-24": httpx.Response(502)}), ["USD"],
                             today=lambda: date(2026, 9, 24))
    assert down.healthcheck().ok is False


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def test_runner_loads_rates_idempotently(source: str) -> None:
    # Test valyutasi (XTB) — sintetik USD/EUR kurslariga tegmaslik uchun.
    body = json.dumps([{"Ccy": "XTB", "Rate": "250.50", "Nominal": "10", "Date": "24.09.2026"}])
    for _ in range(2):
        connector = CbuRatesConnector(client({"2026-09-24": body.encode()}), ["XTB"], days=1,
                                      today=lambda: date(2026, 9, 24), source=source)
        result = Runner(connector, mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                        sleep=lambda _: None).run()
        assert result.status == "success", result
    with etl_transaction() as conn:
        rows = conn.execute(text("SELECT date_id, rate FROM dwh.fx_rate WHERE currency = 'XTB'")
                            ).all()
    assert [(r.date_id, r.rate) for r in rows] == [(20260924, Decimal("25.050000"))]


def test_make_connector_and_worker_job(setting: Callable[[str, object], None]) -> None:
    assert "cbu" in KNOWN_SOURCES
    with pytest.raises(ConfigError, match=r"cbu\.enabled"):
        make_connector("cbu")
    setting("cbu.enabled", True)
    made = make_connector("cbu")
    assert isinstance(made, CbuRatesConnector) and made.currencies[:2] == ["USD", "EUR"]
    assert len(made.dates()) == 7
    jobs = {j.id: j for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert jobs["etl_cbu"].func is worker.run_cbu_job  # shartsiz job, tanasi o'tkazib yuboradi


def test_cbu_job_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(worker, "run_etl_job", lambda source, mode, notifier: calls.append(source))
    assert worker.run_cbu_job(RecordingNotifier()) is None and calls == []


def test_cbu_probe_codes(setting: Callable[[str, object], None]) -> None:
    from app.etl.cbu.client import cbu_probe

    assert cbu_probe() == "not_configured"
    setting("cbu.enabled", True)
    assert cbu_probe(lambda: client({})) == "ok"  # bo'sh massiv ham yaroqli JSON
    html = httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>"))
    assert cbu_probe(lambda: CbuClient(transport=html)) == "format_error"


def test_cli_backfill_validates_range(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["cbu-backfill", "--from", "2026-09-10", "--to", "2026-09-01"]) == 1
    assert cli.main(["cbu-backfill", "--from", "2020-01-01", "--to", "2026-09-01"]) == 1
    assert cli.main(["cbu-backfill", "--from", "2026-09-01", "--to", "2026-09-02"]) == 2
    assert "800" in capsys.readouterr().out


def test_no_etl_transaction_open_during_http(source: str) -> None:
    """M9: ЦБ so'rovi paytida ugk_etl 'idle in transaction' holatida bo'lmasligi kerak."""
    from app.core.db import get_engine

    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        with get_engine("migrator").connect() as conn:
            seen.append(int(conn.execute(text(
                "SELECT count(*) FROM pg_stat_activity WHERE usename = 'ugk_etl' "
                "AND state LIKE 'idle in transaction%'")).scalar_one()))
        body = json.dumps([{"Ccy": "XTB", "Rate": "250.50", "Nominal": "10",
                            "Date": "24.09.2026"}])
        return httpx.Response(200, content=body.encode())

    connector = CbuRatesConnector(CbuClient(transport=httpx.MockTransport(handler)), ["XTB"],
                                  days=1, today=lambda: date(2026, 9, 24), source=source)
    assert connector.buffered is True
    result = Runner(connector, mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                    sleep=lambda _: None).run()
    assert result.status == "success", result
    assert seen and set(seen) == {0}
