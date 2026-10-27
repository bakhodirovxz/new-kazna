import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.context import AuthContext
from app.auth.models import Role, RolePermission, User
from app.auth.permissions import PERMISSIONS
from app.auth.stepup import require_step_up
from app.core import ratelimit
from app.core.db import get_engine, new_session
from app.core.errors import RateLimitedError, ValidationFailed
from app.core.request_meta import ClientMeta
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


# --- step-up: replay/rate-limit/backup-code (review r1: I1, M2, M3) ---


def _actor(user: SeedUser) -> AuthContext:
    return AuthContext(user_id=user.id, username=user.username, full_name="A",
                       role_code="admin", permissions=frozenset(PERMISSIONS), branch_ids=None,
                       session_id=uuid.uuid4())


_META = ClientMeta(ip=None, ua=None, request_id=None)


def test_step_up_sees_step_committed_after_user_was_loaded(
    make_user: Callable[..., SeedUser]
) -> None:
    """I1: get_ctx user'ni qulfsiz yuklaydi; parallel so'rov step'ni commit qilgach FOR UPDATE
    eskirgan obyektni emas, DB qiymatini ko'rishi kerak."""
    user = make_user("admin")
    code = user.next_code()
    with new_session() as s:
        s.get(User, user.id)  # identity map'da eskirgan nusxa
        with get_engine("app").begin() as conn:
            conn.execute(text("UPDATE core.users SET totp_last_step = :s WHERE id = :i"),
                         {"s": user._step, "i": user.id})
        with pytest.raises(ValidationFailed) as exc:
            require_step_up(s, _actor(user), code, _META)
    assert exc.value.code == "step_up_failed"


def test_step_up_rejects_backup_code(make_user: Callable[..., SeedUser]) -> None:
    user = make_user("admin")
    with new_session() as s, pytest.raises(ValidationFailed) as exc:
        require_step_up(s, _actor(user), "ABCD-EFGH-JKLM", _META)
    assert exc.value.code == "step_up_failed"


def test_step_up_rate_limit_counts_only_failures(
    make_user: Callable[..., SeedUser], monkeypatch: pytest.MonkeyPatch
) -> None:
    """M3 (A04b.R1): muvaffaqiyatlilar byudjetni yemaydi; limitdan ko'p xato → 429."""
    monkeypatch.setattr(ratelimit, "STEP_UP_PER_USER", ratelimit.Limit(events=2, window=900))
    user = make_user("admin")
    for _ in range(2):  # 2 ta muvaffaqiyat (limit 2) — 429 yo'q va hisob oshmaydi
        with new_session() as s:
            require_step_up(s, _actor(user), user.next_code(), _META)
            s.commit()
    for _ in range(2):
        with new_session() as s, pytest.raises(ValidationFailed):
            require_step_up(s, _actor(user), "000000", _META)
    with new_session() as s, pytest.raises(RateLimitedError):  # kod tekshirilmasdan rad etiladi
        require_step_up(s, _actor(user), "000000", _META)
