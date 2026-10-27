"""S4 pre-deploy review: HR k-anonimligi (I1), jismoniy yetkazib beruvchi maskasi (M4),
hr.base_url SSRF himoyasi (M5)."""

from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import redis
from fastapi.testclient import TestClient

from app.alerts import hr as hr_alerts  # noqa: F401  (reyestrga yozadi)
from app.alerts.types import REGISTRY, RuleConfig
from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.dwh.reference import DEFAULT_SETTINGS, validate_setting
from app.etl.file_connector import FileConnector
from app.etl.types import Window
from app.etl.zakupki.codes import INDIVIDUAL_NAME
from app.main import create_app
from app.sections.deps import SectionQuery, get_today
from app.sections.period import resolve_period
from app.sections.queries import hr
from app.sections.queries.hr import HIDDEN_REASON, hide_small
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source
from tests.helpers import SeedUser, clear_setting, login, put_setting
from tests.s4_helpers import HrScenario, hr_scenario, purge_s4


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[HrScenario]:
    source = new_source()
    yield hr_scenario(source, publish=True)
    purge_s4(source)


@pytest.fixture
def small_groups() -> Iterator[None]:
    """Ssenariy filiali 90 kishi: chegara 100 bo'lsa u kichik guruh hisoblanadi."""
    put_setting("kadry.min_group", 100)
    yield
    clear_setting("kadry.min_group")


@pytest.fixture
def app_factory() -> Iterator[Callable[[], TestClient]]:
    clients: list[TestClient] = []

    def make() -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def test_min_group_setting_is_tighten_only() -> None:
    assert DEFAULT_SETTINGS["kadry.min_group"] == 5
    assert validate_setting("kadry.min_group", 3) == 3
    assert validate_setting("kadry.min_group", 20) == 20
    for bad in (2, 0, -1, "5", True):
        with pytest.raises(ValueError):
            validate_setting("kadry.min_group", bad)


def test_hide_small_adds_complementary_cells() -> None:
    assert hide_small({"a": 50, "b": 40}, 5) == set()
    assert hide_small({"a": 2, "b": 3, "c": 10}, 5) == {"a", "b"}  # yig'indi 5 >= 5
    # yagona kichik guruh: jami minus boshqalar uni ochardi -> eng kichik ko'rinadigani qo'shiladi
    assert hide_small({"a": 2, "b": 10, "c": 50}, 5) == {"a", "b"}
    assert hide_small({"a": 1, "b": 2}, 5) == {"a", "b"}
    assert hide_small({"a": 1}, 0) == set()


def test_totals_are_suppressed_for_small_group(sc: HrScenario) -> None:
    period = resolve_period("m08", TEST_AS_OF)
    sel = BranchSel(sc.branch_id, True)
    with new_session() as db:
        apply_rls(db, None)
        full = hr.totals(db, sel, period, [sc.salary_code], min_group=5)
        small = hr.totals(db, sel, period, [sc.salary_code], min_group=100)
    assert full.avg_salary == 2.0 and not full.suppressed
    assert small.suppressed and small.avg_salary is None and small.turnover is None
    assert small.overtime_per_employee is None and small.payroll_share is None
    assert (small.plan, small.fact) == (100.0, 90.0)  # shtat/fakt (tuzilma) ko'rinadi


def _check_hidden(body: dict[str, Any]) -> None:
    k = body["kpis"]
    assert k["suppressed"] is True and k["suppressed_reason"] == HIDDEN_REASON
    for field in ("payroll", "avg_salary", "payroll_share", "hired", "fired", "turnover",
                  "overtime", "overtime_per_employee"):
        assert k[field] is None, field
    assert k["fact"] == 90.0
    for branch in body["branches"]:
        assert branch["suppressed"] is True and branch["suppressed_reason"] == HIDDEN_REASON
        assert all(branch[f] is None for f in ("payroll", "avg_salary", "hired", "fired",
                                               "overtime", "overtime_per_employee"))
    for month in body.get("months", []):
        assert month["avg_salary"] is None and month["payroll"] is None


def test_api_hides_small_groups_for_leadership_and_branch_roles(
        sc: HrScenario, small_groups: None, app_factory: Callable[[], TestClient],
        make_user: Callable[..., SeedUser]) -> None:
    leader = login(app_factory(), make_user("rukovodstvo"))
    econ = login(app_factory(), make_user("economist_filiala", branch_ids=(sc.branch_id,)))
    for client, params in ((leader, {"per": "m08", "br": sc.branch_id}),
                           (econ, {"per": "m08"})):
        for page in ("svod", "fot", "dvizhenie", "chislennost"):
            body = client.get(f"/api/v1/kadry/{page}", params=params).json()
            _check_hidden(body)
    svod = leader.get("/api/v1/kadry/svod", params={"per": "m08", "br": sc.branch_id}).json()
    assert all(c["value"] is None and c["suppressed"] for c in svod["categories"])


def test_default_threshold_keeps_normal_groups_visible(
        sc: HrScenario, app_factory: Callable[[], TestClient],
        make_user: Callable[..., SeedUser]) -> None:
    client = login(app_factory(), make_user("rukovodstvo"))
    body = client.get("/api/v1/kadry/svod",
                      params={"per": "m08", "br": sc.branch_id}).json()
    assert body["kpis"]["suppressed"] is False and body["kpis"]["fact"] == 90.0
    assert body["kpis"]["avg_salary"] is not None  # ФОТ statyasi bu modulda standart
    assert body["kpis"]["suppressed_reason"] is None


def test_alert_inputs_are_suppressed(sc: HrScenario, small_groups: None) -> None:
    rule = RuleConfig("x", "x", "kadry", "svod", "warning", {"op": ">", "value": 0})
    q = SectionQuery(sc.branch_id, "m08", TEST_AS_OF, None)
    with new_session() as db:
        apply_rls(db, None)
        assert REGISTRY["turnover"](db, q, rule) is None
        assert REGISTRY["overtime"](db, q, rule) is None


def test_hr_base_url_rejects_internal_hosts() -> None:
    for bad in ("https://127.0.0.1", "https://127.1.2.3:8443/api", "https://169.254.169.254",
                "https://localhost", "https://localhost:8443", "https://0.0.0.0",
                "https://2130706433", "https://0x7f.1", "https://metadata.google.internal",
                "https://app.localhost", "http://hr.test", "https://224.0.0.1"):
        with pytest.raises(ValueError):
            validate_setting("hr.base_url", bad)
    for good in ("", "https://hr-api.uzgidro.uz", "https://10.1.2.3", "https://172.16.0.5/api",
                 "https://192.168.1.5:8443/api"):
        assert validate_setting("hr.base_url", good) == good


def test_file_path_masks_individual_suppliers(tmp_path: Path) -> None:
    (tmp_path / "dim_counterparty.csv").write_text(
        "code;name;kind;inn\n"
        "S-1;Иванов Иван Иванович;supplier;12345678901234\n"
        "S-2;ООО «Альфа»;supplier;301234567\n", encoding="utf-8")

    class Collect:
        def __init__(self) -> None:
            self.rows: list[dict[str, Any]] = []

        def add(self, target: str, row: Any) -> None:
            self.rows.append(dict(row))

    sink = Collect()
    FileConnector(tmp_path, source="x").extract(Window(date(2024, 1, 1), TEST_AS_OF), sink)
    by_code = {r["code"]: r for r in sink.rows}
    assert by_code["S-1"]["name"] == INDIVIDUAL_NAME and by_code["S-1"]["inn"] is None
    assert "Иванов" not in str(sink.rows) and "12345678901234" not in str(sink.rows)
    assert by_code["S-2"]["name"] == "ООО «Альфа»" and by_code["S-2"]["inn"] == "301234567"
