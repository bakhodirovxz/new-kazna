from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import get_engine
from app.dwh import builds
from app.etl.db import etl_transaction
from app.etl.runner import RunResult
from app.main import create_app
from tests.etl_helpers import STEP_NAMES
from tests.helpers import SeedUser, login


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


@pytest.fixture
def admin(client: TestClient, make_user: Callable[..., SeedUser]) -> SeedUser:
    user = make_user("admin")
    login(client, user)
    return user


def _audit(action: str, object_id: str) -> int:
    with get_engine("app").connect() as conn:
        return int(conn.execute(
            text("SELECT count(*) FROM core.audit_log WHERE action = :a AND object_id = :o"),
            {"a": action, "o": object_id}).scalar_one())


def test_permissions_are_enforced(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("rukovodstvo"))
    assert client.get("/api/v1/admin/etl/runs").status_code == 403
    assert client.get("/api/v1/admin/builds").status_code == 403
    assert client.get("/api/v1/admin/alert-rules").status_code == 403
    assert client.get("/api/v1/admin/settings").status_code == 403


@pytest.mark.usefixtures("admin")
def test_trigger_run_enqueues_request(client: TestClient) -> None:
    r = client.post("/api/v1/admin/etl/run", json={"source": "synthetic", "mode": "incremental"})
    assert r.status_code == 202, r.text
    request_id = r.json()["request_id"]
    try:
        with etl_transaction() as conn:
            status = conn.execute(text("SELECT status FROM core.etl_requests WHERE id = :i"),
                                  {"i": request_id}).scalar_one()
        assert status == "pending" and r.json()["status"] == "pending"
        assert _audit("admin.etl.run_requested", str(request_id)) == 1
    finally:
        with etl_transaction() as conn:  # worker testlari bu so'rovni bajarmasin
            conn.execute(text("UPDATE core.etl_requests SET status = 'failed' WHERE id = :i"),
                         {"i": request_id})


@pytest.mark.usefixtures("admin")
def test_trigger_unknown_source_or_mode_is_422(client: TestClient) -> None:
    r = client.post("/api/v1/admin/etl/run", json={"source": "oracle", "mode": "full"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_source"
    r = client.post("/api/v1/admin/etl/run", json={"source": "file", "mode": "hourly"})
    assert r.status_code == 422


@pytest.mark.usefixtures("admin")
def test_runs_list_page_upper_bound_is_422(client: TestClient) -> None:
    """T13: page cheksiz bo'lsa OFFSET katta qiymatda DB'ni yuklaydi — le=100000."""
    r = client.get("/api/v1/admin/etl/runs?page=100001")
    assert r.status_code == 422


@pytest.mark.usefixtures("admin")
def test_runs_list_and_detail(client: TestClient, synthetic_run: RunResult) -> None:
    page = client.get("/api/v1/admin/etl/runs", params={"page_size": 500}).json()
    assert synthetic_run.run_id in [r["id"] for r in page["items"]]
    detail = client.get(f"/api/v1/admin/etl/runs/{synthetic_run.run_id}").json()
    assert detail["run"]["status"] == "success"
    assert [s["name"] for s in detail["steps"]] == list(STEP_NAMES)
    assert client.get("/api/v1/admin/etl/runs/999999999").status_code == 404


@pytest.mark.usefixtures("admin")
def test_builds_list_and_rollback(client: TestClient, published_synthetic: int) -> None:
    with etl_transaction() as conn:
        newer = builds.create_build(conn, None)
        builds.mark_ready(conn, newer)
        builds.publish(conn, newer, keep=3)
    listed = client.get("/api/v1/admin/builds").json()
    assert next(b for b in listed if b["active"])["build_id"] == newer
    r = client.post("/api/v1/admin/builds/rollback", json={})
    assert r.status_code == 200, r.text
    assert r.json()["build_id"] == published_synthetic and r.json()["active"] is True
    assert _audit("admin.build.rolled_back", str(published_synthetic)) >= 1
    missing = client.post("/api/v1/admin/builds/rollback", json={"build_id": 999999999})
    assert missing.status_code == 409 and missing.json()["error"]["code"] == "build_not_available"


@pytest.mark.usefixtures("admin")
def test_alert_rule_update_creates_version_and_audit(client: TestClient) -> None:
    before = next(r for r in client.get("/api/v1/admin/alert-rules").json()
                  if r["code"] == "turnover")
    r = client.patch("/api/v1/admin/alert-rules/turnover", json={"value": 0.1, "level": "critical"})
    assert r.status_code == 200, r.text
    after = r.json()
    try:
        assert after["version"] == before["version"] + 1
        assert after["threshold"]["value"] == 0.1 and after["threshold"]["op"] == ">"
        assert after["level"] == "critical"
        history = client.get("/api/v1/admin/alert-rules/turnover/history").json()
        assert [h["version"] for h in history][:2] == [after["version"], before["version"]]
        assert _audit("admin.alert_rule.updated", "turnover") >= 1
        assert client.patch("/api/v1/admin/alert-rules/turnover",
                            json={"op": "!="}).status_code == 422
        assert client.patch("/api/v1/admin/alert-rules/nope", json={"value": 1}).status_code == 404
    finally:
        client.patch("/api/v1/admin/alert-rules/turnover",
                     json={"value": before["threshold"]["value"], "level": before["level"]})


@pytest.mark.usefixtures("admin")
def test_fin_assumptions_update(client: TestClient) -> None:
    item = {"scenario": "tariff", "year": 2027, "key": "tariff_growth"}
    r = client.put("/api/v1/admin/fin-assumptions", json={"items": [{**item, "value": 0.05}]})
    assert r.status_code == 200, r.text
    try:
        current = client.get("/api/v1/admin/fin-assumptions", params={"scenario": "tariff"}).json()
        row = next(x for x in current if x["year"] == 2027 and x["key"] == "tariff_growth")
        assert row["value"] == 0.05 and row["version"] >= 2
        bad_key = client.put("/api/v1/admin/fin-assumptions",
                             json={"items": [{**item, "key": "magic", "value": 1}]})
        assert bad_key.status_code == 422
        bad_year = client.put("/api/v1/admin/fin-assumptions",
                              json={"items": [{**item, "year": 2040, "value": 1}]})
        assert bad_year.status_code == 422
        scalar_year = client.put("/api/v1/admin/fin-assumptions", json={"items": [
            {"scenario": "base", "year": 2027, "key": "tariff_start", "value": 700}]})
        assert scalar_year.status_code == 422
        big = client.put("/api/v1/admin/fin-assumptions", json={"items": [
            {"scenario": "base", "year": 2026, "key": "tariff_start", "value": 750}]})
        assert big.status_code == 200, big.text
        client.put("/api/v1/admin/fin-assumptions", json={"items": [
            {"scenario": "base", "year": 2026, "key": "tariff_start", "value": 705}]})
    finally:
        client.put("/api/v1/admin/fin-assumptions", json={"items": [{**item, "value": 0.04}]})


@pytest.mark.usefixtures("admin")
def test_settings_update_and_validation(client: TestClient) -> None:
    r = client.put("/api/v1/admin/settings/freshness.max_age_hours", json={"value": 8})
    assert r.status_code == 200 and r.json()["value"] == 8
    try:
        listed = {s["key"]: s for s in client.get("/api/v1/admin/settings").json()}
        assert listed["freshness.max_age_hours"]["value"] == 8
        zero = client.put("/api/v1/admin/settings/freshness.max_age_hours", json={"value": 0})
        assert zero.status_code == 422 and zero.json()["error"]["code"] == "invalid_setting"
        assert client.put("/api/v1/admin/settings/no.such", json={"value": 1}).status_code == 404
        assert _audit("admin.setting.updated", "freshness.max_age_hours") >= 1
    finally:
        client.put("/api/v1/admin/settings/freshness.max_age_hours", json={"value": 6})


_VERSIONED = {
    "core.settings": ("(key, version, value) VALUES ('guard.t', 1, '1')", "key = 'guard.t'"),
    "core.alert_rules": (
        "(code, version, title, section, page, threshold, level) "
        "VALUES ('guard_t', 1, 't', 's', 'p', '{}', 'warning')", "code = 'guard_t'"),
    "core.fin_assumptions": (
        "(scenario, year, key, version, value) VALUES ('base', 2026, 'guard_t', 1, 1)",
        "key = 'guard_t'"),
}


@pytest.mark.parametrize("table", list(_VERSIONED))
def test_versioned_tables_are_append_only_for_app_role(table: str) -> None:
    from sqlalchemy.exc import DBAPIError

    cols, where = _VERSIONED[table]
    value_col = {"core.settings": "value = '2'", "core.alert_rules": "level = 'critical'",
                 "core.fin_assumptions": "value = 2"}[table]
    with get_engine("app").connect() as conn:
        conn.execute(text(f"INSERT INTO {table} {cols}"))
        for stmt in (f"UPDATE {table} SET {value_col} WHERE {where}",
                     f"UPDATE {table} SET updated_by = 1 WHERE {where}"):
            sp = conn.begin_nested()
            with pytest.raises(DBAPIError, match="permission denied"):
                conn.execute(text(stmt))
            sp.rollback()
        # true -> false, nothing else changed: allowed; false -> true: rejected by the trigger
        conn.execute(text(f"UPDATE {table} SET is_current = false WHERE {where}"))
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text(f"UPDATE {table} SET is_current = true WHERE {where}"))
        conn.rollback()


def test_past_alert_rule_version_is_untouched_by_edit(client: TestClient, admin: SeedUser) -> None:
    snap = ("SELECT to_jsonb(r) FROM core.alert_rules r WHERE code = 'turnover' "
            "AND version = :v")
    before = client.get("/api/v1/admin/alert-rules").json()
    cur = next(r for r in before if r["code"] == "turnover")
    with get_engine("app").connect() as conn:
        old = conn.execute(text(snap), {"v": cur["version"]}).scalar_one()
    client.patch("/api/v1/admin/alert-rules/turnover", json={"value": 0.123})
    try:
        with get_engine("app").connect() as conn:
            new = conn.execute(text(snap), {"v": cur["version"]}).scalar_one()
        assert {k: v for k, v in new.items() if k != "is_current"} == \
               {k: v for k, v in old.items() if k != "is_current"}
        assert new["is_current"] is False
    finally:
        client.patch("/api/v1/admin/alert-rules/turnover",
                     json={"value": cur["threshold"]["value"]})
