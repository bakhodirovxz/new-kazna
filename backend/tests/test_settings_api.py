import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.models import Role, RolePermission
from app.core.db import get_engine, new_session
from app.main import create_app
from tests.helpers import SeedUser, clear_setting, create_user, login

URL = "/api/v1/admin/settings"
IDLE = "security.session_idle_minutes"
REASON = "Письмо ИБ №7"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


@pytest.fixture
def restore() -> Iterator[None]:
    yield
    for key in (IDLE, "builds.keep"):
        clear_setting(key)


def _role_user(*perms: str) -> SeedUser:
    code = f"r_{uuid.uuid4().hex[:8]}"
    with new_session() as s:
        role = Role(code=code, name=f"Тест {code}", scope_all=True, is_system=False)
        s.add(role)
        s.flush()
        for perm in perms:
            s.add(RolePermission(role_id=role.id, permission_code=perm))
        s.commit()
    return create_user(code)


def _last_audit(action: str, user_id: int) -> dict[str, Any]:
    with get_engine("app").connect() as conn:
        row = conn.execute(text("SELECT details, result FROM core.audit_log WHERE action = :a "
                                "AND user_id = :u ORDER BY id DESC LIMIT 1"),
                           {"a": action, "u": user_id}).one()
    return {"details": row.details, "result": row.result}


def _error(r: Any) -> dict[str, Any]:
    return dict(r.json()["error"])


def test_list_has_metadata_and_respects_permissions(client: TestClient) -> None:
    login(client, _role_user("admin:settings"))
    keys = {s["key"]: s for s in client.get(URL).json()}
    assert IDLE not in keys and "smtp.host" not in keys
    keep = keys["builds.keep"]
    assert (keep["kind"], keep["lo"], keep["hi"], keep["perm"], keep["apply"], keep["default"]) \
        == ("int", 2, 10, "admin:settings", "next_run", 3)
    assert keys["retention.fact_years"]["guarded"] is True
    assert keys["retention.fact_years"]["step_up"] is False


def test_security_admin_sees_only_security_keys(client: TestClient) -> None:
    login(client, _role_user("admin:security"))
    listed = client.get(URL).json()
    assert listed and {s["perm"] for s in listed} == {"admin:security"}
    idle = next(s for s in listed if s["key"] == IDLE)
    assert (idle["step_up"], idle["category"], idle["value"]) == (True, "security", 30)


def test_settings_admin_cannot_change_security_key(client: TestClient) -> None:
    user = _role_user("admin:settings")
    login(client, user)
    r = client.put(f"{URL}/{IDLE}", json={"value": 20, "reason": REASON, "otp": "123456"})
    assert r.status_code == 403
    assert _last_audit("security.access_denied", user.id)["result"] == "denied"


@pytest.mark.usefixtures("restore")
def test_guarded_key_needs_reason_and_fresh_totp(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    admin = make_user("admin")
    login(client, admin)
    path = f"{URL}/{IDLE}"
    assert _error(client.put(path, json={"value": 20}))["code"] == "reason_required"
    missing = _error(client.put(path, json={"value": 20, "reason": REASON}))
    assert (missing["code"], missing["params"]["fields"]) == ("step_up_required", ["otp"])
    bad = client.put(path, json={"value": 20, "reason": REASON, "otp": "12345"})
    assert bad.status_code == 422 and _error(bad)["code"] == "step_up_failed"
    assert _last_audit("auth.step_up.failed", admin.id)["result"] == "fail"
    ok = client.put(path, json={"value": 20, "reason": REASON, "otp": admin.next_code(),
                                "expected_version": 0})
    assert ok.status_code == 200, ok.text
    assert (ok.json()["value"], ok.json()["source"], ok.json()["version"]) == (20, "panel", 1)
    audit = _last_audit("admin.setting.updated", admin.id)["details"]
    assert (audit["before"], audit["after"], audit["reason"]) == (None, 20, REASON)


@pytest.mark.usefixtures("restore")
def test_step_up_rejects_replayed_code(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    admin = make_user("admin")
    login(client, admin)
    code = admin.next_code()
    path = f"{URL}/{IDLE}"
    assert client.put(path, json={"value": 25, "reason": REASON, "otp": code}).status_code == 200
    again = client.put(path, json={"value": 20, "reason": REASON, "otp": code})
    assert again.status_code == 422 and _error(again)["code"] == "step_up_failed"


@pytest.mark.usefixtures("restore")
def test_stale_expected_version_is_409(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user("admin"))
    version = next(s for s in client.get(URL).json() if s["key"] == "builds.keep")["version"]
    path = f"{URL}/builds.keep"
    assert client.put(path, json={"value": 4, "expected_version": version}).status_code == 200
    stale = client.put(path, json={"value": 5, "expected_version": version})
    assert stale.status_code == 409 and _error(stale)["code"] == "conflict_modified"


def test_out_of_range_reports_bounds(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user("admin"))
    r = client.put(f"{URL}/builds.keep", json={"value": 11})
    err = _error(r)
    assert r.status_code == 422 and err["code"] == "invalid_setting"
    assert (err["params"]["fields"], err["params"]["lo"], err["params"]["hi"]) == (["value"], 2, 10)


def test_integration_fields_are_not_edited_here_but_have_history(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user("admin"))
    assert client.put(f"{URL}/smtp.host", json={"value": "x"}).status_code == 404
    assert client.get(f"{URL}/smtp.host/history").json() == []
    assert client.get(f"{URL}/no.such/history").status_code == 404


def test_history_lists_versions_newest_first(
    client: TestClient, make_user: Callable[..., SeedUser],
    setting: Callable[[str, object], None],
) -> None:
    setting("builds.keep", 4)
    setting("builds.keep", 5)
    login(client, make_user("admin"))
    rows = client.get(f"{URL}/builds.keep/history").json()
    assert [r["value"] for r in rows[:2]] == [5, 4]
