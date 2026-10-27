from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import worker
from app.core.config import ConfigError, get_settings
from app.etl.askue import live
from app.etl.askue.live import GesLiveClient, LiveError, map_snapshot, poll_power
from app.etl.askue.registry import AskueStation
from app.etl.db import etl_transaction
from app.etl.types import ConnectorUnavailableError
from app.main import create_app
from app.sections.deps import get_today
from app.sections.proizvodstvo import get_now
from tests.etl_helpers import TEST_AS_OF, RecordingNotifier
from tests.helpers import SeedUser, clear_setting, login, put_setting

FIXTURE = (Path(__file__).parent / "fixtures" / "askue" / "live_ok.json").read_bytes()
URL = "https://treplex.test/api/cascades/ges"
T1 = datetime(2026, 9, 25, 5, 40, tzinfo=UTC)
STATIONS = [AskueStation(code="CHARVAK-1", name="Chorvoq  GES", branch_code="UGE-02"),
            AskueStation(code="CHIRCHIQ-7", name="chirchiq ges-7", branch_code="UGE-03")]


def fake(response: httpx.Response | Callable[[httpx.Request], httpx.Response]) -> GesLiveClient:
    handler = response if callable(response) else (lambda _r: response)
    return GesLiveClient(URL, transport=httpx.MockTransport(handler))


def ok_client() -> GesLiveClient:
    return fake(httpx.Response(200, content=FIXTURE))


def test_parse_fixture() -> None:
    client = ok_client()
    resp = client.fetch()
    assert client.http.trust_env is False and client.http.follow_redirects is False
    assert resp.date == "25.09.2026 10:40" and len(resp.cascades) == 1
    st = resp.cascades[0].stations
    assert [(s.ges, s.power, s.agg) for s in st] == [
        ("Chorvoq GES", Decimal("380.5"), (3, 1, 0)), ("Chirchiq GES-7", Decimal("32"), (2, 0, 1)),
        ("Yangi GES", Decimal("0"), (0, 2, 0))]


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="<html>Ошибка</html>"),
    httpx.Response(200, json={"cascades": "x"}),
    httpx.Response(200, json={"cascades": [{"name": "K", "stations": [
        {"ges": "A", "power": "-5"}]}]}),
    httpx.Response(200, json={"cascades": [{"name": "K", "stations": [
        {"ges": "A", "power": "1", "agg": "a/b"}]}]}),
    httpx.Response(302, headers={"location": "https://evil.test/"}),
    httpx.Response(404),
])
def test_bad_responses_are_not_retryable(response: httpx.Response) -> None:
    with pytest.raises(LiveError) as exc:
        fake(response).fetch()
    assert not isinstance(exc.value, ConnectorUnavailableError)


def test_transient_errors_are_retryable_and_size_capped() -> None:
    with pytest.raises(ConnectorUnavailableError, match="503"):
        fake(httpx.Response(503)).fetch()

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ConnectorUnavailableError, match="тайм-аут"):
        fake(timeout).fetch()
    big = GesLiveClient(URL, max_bytes=100,
                        transport=httpx.MockTransport(lambda _r: httpx.Response(200,
                                                                               content=FIXTURE)))
    with pytest.raises(LiveError, match="больше"):
        big.fetch()
    with pytest.raises(ConfigError):
        GesLiveClient("http://treplex.test/api/cascades/ges")


def test_map_snapshot_normalizes_names() -> None:
    snaps, unmapped = map_snapshot(ok_client().fetch(), STATIONS)
    assert [(s.station, s.branch_code, s.power_mw, s.units_working, s.units_repair)
            for s in snaps] == [("CHARVAK-1", "UGE-02", Decimal("380.5"), 3, 0),
                                ("CHIRCHIQ-7", "UGE-03", Decimal("32"), 2, 1)]
    assert unmapped == ["Yangi GES"]
    assert snaps[0].cascade_name == "Chirchiq-Bo'zsuv GESlar kaskadi"


def _clear() -> None:
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM dwh.fact_power_snapshot WHERE station = ANY(:s)"),
                     {"s": [s.code for s in STATIONS]})


@pytest.fixture
def stations() -> Iterator[None]:
    _clear()
    put_setting("askue.stations", [s.model_dump() for s in STATIONS])
    yield
    put_setting("askue.stations", [])
    clear_setting("askue.live_url")
    _clear()


def _count() -> int:
    with etl_transaction() as conn:
        return int(conn.execute(text("SELECT count(*) FROM dwh.fact_power_snapshot "
                                     "WHERE station = ANY(:s)"),
                                {"s": [s.code for s in STATIONS]}).scalar_one())


def test_poll_stores_and_prunes(stations: None) -> None:
    settings = get_settings()
    first = poll_power(settings, client=ok_client(), now=T1 - timedelta(days=40))
    assert (first.stored, first.unmapped) == (2, ["Yangi GES"])
    result = poll_power(settings, client=ok_client(), now=T1 + timedelta(seconds=37))
    assert result.snap_at == T1 and result.stored == 2 and result.pruned == 2
    with etl_transaction() as conn:
        rows = conn.execute(text("SELECT station, snap_at, power_mw, source_date "
                                 "FROM dwh.fact_power_snapshot WHERE station = ANY(:s) "
                                 "ORDER BY station"), {"s": [s.code for s in STATIONS]}).all()
    assert [(r.station, r.snap_at, r.power_mw) for r in rows] == [
        ("CHARVAK-1", T1, Decimal("380.5000")), ("CHIRCHIQ-7", T1, Decimal("32.0000"))]
    assert rows[0].source_date == "25.09.2026 10:40"


def test_poll_failure_keeps_last_snapshot(stations: None,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    poll_power(settings, client=ok_client(), now=T1)
    with pytest.raises(ConnectorUnavailableError):
        poll_power(settings, client=fake(httpx.Response(503)), now=T1 + timedelta(minutes=10))
    put_setting("askue.live_url", URL)
    monkeypatch.setattr(live, "GesLiveClient", lambda *a, **k: fake(httpx.Response(502)))
    live.poll_power_job(settings)  # xatoni log qiladi, ko'tarmaydi
    assert _count() == 2


@pytest.fixture
def app_factory() -> Iterator[Callable[[datetime], TestClient]]:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)
    clients: list[TestClient] = []

    def make(now: datetime) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        app.dependency_overrides[get_now] = lambda: now
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def test_moshchnost_stale_and_empty(stations: None, app_factory: Callable[[datetime], TestClient],
                                    make_user: Callable[..., SeedUser]) -> None:
    empty = login(app_factory(T1), make_user("rukovodstvo")).get("/api/v1/proizvodstvo/moshchnost")
    assert empty.status_code == 200, empty.text
    assert empty.json()["has_source"] is False and empty.json()["stations"] == []
    poll_power(get_settings(), client=ok_client(), now=T1)
    fresh = login(app_factory(T1 + timedelta(minutes=5)), make_user("rukovodstvo")).get(
        "/api/v1/proizvodstvo/moshchnost").json()
    assert (fresh["has_source"], fresh["stale"], fresh["total_mw"]) == (True, False, 412.5)
    assert (fresh["units_working"], fresh["units_reserve"], fresh["units_repair"]) == (5, 1, 1)
    assert fresh["snap_at"].startswith("2026-09-25T05:40") and fresh["source_date"]
    assert [s["station"] for s in fresh["stations"]] == ["CHARVAK-1", "CHIRCHIQ-7"]
    old = login(app_factory(T1 + timedelta(hours=2)), make_user("rukovodstvo")).get(
        "/api/v1/proizvodstvo/moshchnost").json()
    assert old["stale"] is True and old["total_mw"] == 412.5
    econ = login(app_factory(T1), make_user("economist_filiala", branch_ids=(3,)))
    own = econ.get("/api/v1/proizvodstvo/moshchnost").json()
    assert [s["station"] for s in own["stations"]] == ["CHIRCHIQ-7"] and own["total_mw"] == 32.0
    assert econ.get("/api/v1/proizvodstvo/moshchnost", params={"br": 2}).status_code == 403
    kazna = login(app_factory(T1), make_user("spec_kazna"))
    assert kazna.get("/api/v1/proizvodstvo/moshchnost").status_code == 403


def test_live_check_cli(stations: None) -> None:
    out: list[str] = []
    settings = get_settings()
    assert live.askue_live_check_command(settings, out.append) == 2
    assert live.askue_live_check_command(settings, out.append, client=ok_client()) == 0
    assert any("CHARVAK-1" in line for line in out) and any("Yangi GES" in line for line in out)
    assert live.askue_live_check_command(settings, out.append,
                                         client=fake(httpx.Response(503))) == 1


def test_scheduler_adds_live_job_and_skips_without_url(stations: None) -> None:
    jobs = {j.id: j for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert "askue_live" in jobs
    live.poll_power_job(get_settings())  # askue.live_url bo'sh — o'tkazib yuboradi, tarmoq yo'q
    assert _count() == 0


def test_askue_live_probe_codes(stations: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.etl import probes

    assert probes.PROBES["askue_live"]() == "not_configured"
    put_setting("askue.live_url", URL)
    for response, code in ((httpx.Response(200, content=FIXTURE), "ok"),
                           (httpx.Response(200, text="<html>"), "format_error"),
                           (httpx.Response(404), "http_error"),
                           (httpx.Response(503), "connect_failed")):
        monkeypatch.setattr(probes, "GesLiveClient", lambda *a, _r=response, **k: fake(_r))
        assert probes.PROBES["askue_live"]() == code


def test_decoding_error_is_not_retryable() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.DecodingError("bad gzip", request=request)

    with pytest.raises(LiveError) as exc:
        fake(broken).fetch()
    assert not isinstance(exc.value, ConnectorUnavailableError)


def test_overall_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live, "DEADLINE", -1.0)
    with pytest.raises(ConnectorUnavailableError, match="тайм-аут"):
        ok_client().fetch()
