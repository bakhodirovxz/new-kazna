"""2FA majburiy emas (qaror 27.10.2026): `security.mfa_required`, taklif, keyin ulash."""

from collections.abc import Callable, Iterator
from typing import Any

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.context import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core import sysconfig
from app.core.db import get_engine
from app.main import create_app
from tests.helpers import SeedUser, clear_setting, login, put_setting

KEY = "security.mfa_required"
A = "/api/v1/auth"
REASON = "Решение комиссии ИБ"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    clear_setting(KEY)
    yield
    clear_setting(KEY)


def _post_login(client: TestClient, user: SeedUser) -> Any:
    return client.post(f"{A}/login", json={"username": user.username, "password": user.password})


def _audit(user_id: int, action: str) -> int:
    with get_engine("app").connect() as conn:
        return int(conn.execute(
            text("SELECT count(*) FROM core.audit_log WHERE user_id = :u AND action = :a"),
            {"u": user_id, "a": action}).scalar_one())


def _as_user(client: TestClient, user: SeedUser) -> dict[str, Any]:
    r = _post_login(client, user)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next"] == "done" and body["mfa_token"] is None, body
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    return dict(body)


def test_setting_registered_off_by_default() -> None:
    d = sysconfig.REGISTRY[KEY]
    assert (d.default, d.kind, d.category, d.perm.value, d.step_up) == (
        False, "bool", "security", "admin:security", True)
    assert sysconfig.value(KEY) is False


def test_no_totp_login_creates_session_and_offers(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("rukovodstvo", totp=False)
    body = _as_user(client, user)
    assert body["user"]["username"] == user.username
    assert body["user"]["mfa_enabled"] is False and body["user"]["mfa_offer"] is True
    assert client.cookies.get(SESSION_COOKIE)
    assert client.get(f"{A}/me").json()["mfa_offer"] is True


def test_wrong_password_never_creates_session(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("rukovodstvo", totp=False)
    r = client.post(f"{A}/login", json={"username": user.username, "password": "xato-parol-1"})
    assert r.status_code == 401
    assert SESSION_COOKIE not in client.cookies


def test_required_keeps_mandatory_enrollment(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    put_setting(KEY, True)
    r = _post_login(client, make_user("rukovodstvo", totp=False))
    assert r.json()["next"] == "mfa_enroll" and r.json()["mfa_token"]
    assert SESSION_COOKIE not in client.cookies


@pytest.mark.parametrize("required", [False, True])
def test_totp_user_always_verifies(
    client: TestClient, make_user: Callable[..., SeedUser], required: bool
) -> None:
    if required:
        put_setting(KEY, True)
    r = _post_login(client, make_user("rukovodstvo"))
    assert r.json()["next"] == "mfa_verify" and r.json()["mfa_token"]
    assert SESSION_COOKIE not in client.cookies


def test_must_change_password_still_enforced(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("rukovodstvo", totp=False, must_change=True)
    body = _as_user(client, user)
    assert body["user"]["must_change_password"] is True
    assert client.get(f"{A}/sessions").status_code == 403  # parol almashguncha boshqa API yopiq


def test_dismiss_is_audited_and_hides_offer(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("rukovodstvo", totp=False)
    _as_user(client, user)
    assert client.post(f"{A}/2fa/offer/dismiss").status_code == 204
    assert client.get(f"{A}/me").json()["mfa_offer"] is False
    assert _audit(user.id, "auth.mfa_offer_dismissed") == 1
    again = TestClient(client.app, base_url="https://testserver")
    assert _as_user(again, user)["user"]["mfa_offer"] is False


def test_offer_returns_once_after_password_change(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("rukovodstvo", totp=False)
    _as_user(client, user)
    client.post(f"{A}/2fa/offer/dismiss")
    with get_engine("migrator").begin() as conn:
        conn.execute(text("UPDATE core.users SET password_changed_at = now() WHERE id = :u"),
                     {"u": user.id})
    assert client.get(f"{A}/me").json()["mfa_offer"] is True


def test_offer_off_when_required(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user("rukovodstvo", totp=False)
    _as_user(client, user)
    put_setting(KEY, True)
    assert client.get(f"{A}/me").json()["mfa_offer"] is False


def _begin(client: TestClient, user: SeedUser, password: str | None = None) -> Any:
    return client.post(f"{A}/2fa/enroll/begin", json={"password": password or user.password})


def test_later_enrollment_is_session_bound_and_keeps_absolute_expiry(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("rukovodstvo", totp=False)
    _as_user(client, user)
    with get_engine("app").connect() as conn:
        before = conn.execute(text(
            "SELECT absolute_expires_at FROM core.sessions "
            "WHERE user_id = :u AND revoked_at IS NULL"),
            {"u": user.id}).scalar_one()
    begin = _begin(client, user)
    assert begin.status_code == 200, begin.text
    assert "mfa_token" not in begin.json()  # token yo'q: sessiyaga bog'langan
    secret = begin.json()["secret"]
    done = client.post(f"{A}/2fa/enroll/finish", json={"code": pyotp.TOTP(secret).now()})
    assert done.status_code == 200, done.text
    assert done.json()["user"]["mfa_enabled"] is True and done.json()["backup_codes"]
    assert _audit(user.id, "auth.mfa.enrolled") == 1
    with get_engine("app").connect() as conn:
        after = conn.execute(text(
            "SELECT absolute_expires_at FROM core.sessions "
            "WHERE user_id = :u AND revoked_at IS NULL"),
            {"u": user.id}).scalars().all()
    assert after == [before]  # yangi 12 soatlik sessiya berilmadi, eskisi bekor qilindi
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    assert _begin(client, user).status_code == 409  # allaqachon ulangan


def test_enroll_finish_from_another_session_is_rejected(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("rukovodstvo", totp=False)
    _as_user(client, user)
    secret = _begin(client, user).json()["secret"]
    other = TestClient(client.app, base_url="https://testserver")
    _as_user(other, user)
    r = other.post(f"{A}/2fa/enroll/finish", json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 401 and r.json()["error"]["code"] == "mfa_expired"


def test_logout_and_new_login_kill_open_enroll_challenge(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("rukovodstvo", totp=False)
    _as_user(client, user)
    _begin(client, user)

    def open_challenges() -> int:
        with get_engine("app").connect() as conn:
            return int(conn.execute(text(
                "SELECT count(*) FROM core.mfa_challenges WHERE user_id = :u AND used_at IS NULL"),
                {"u": user.id}).scalar_one())

    assert open_challenges() == 1
    assert client.post(f"{A}/logout").status_code == 204
    assert open_challenges() == 0
    # yangi parolli kirish ham eskirgan challenge'larni tozalaydi
    _as_user(client, user)
    _begin(client, user)
    again = TestClient(client.app, base_url="https://testserver")
    _as_user(again, user)
    assert open_challenges() == 0


def test_enroll_begin_requires_current_password_and_counts_toward_lockout(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("rukovodstvo", totp=False)
    _as_user(client, user)
    bad = _begin(client, user, "Noto'g'ri-Parol-1")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_current_password"
    with get_engine("app").connect() as conn:
        failed = conn.execute(text("SELECT failed_logins FROM core.users WHERE id = :u"),
                              {"u": user.id}).scalar_one()
    assert failed == 1
    assert _audit(user.id, "auth.password.change_fail") == 1
    assert _begin(client, user).status_code == 200


def test_begin_and_dismiss_require_session(client: TestClient) -> None:
    assert client.post(f"{A}/2fa/enroll/begin", json={"password": "x"}).status_code == 401
    assert client.post(f"{A}/2fa/enroll/finish", json={"code": "123456"}).status_code == 401
    assert client.post(f"{A}/2fa/offer/dismiss").status_code == 401


def test_step_up_unavailable_without_totp(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("admin", totp=False)
    _as_user(client, user)
    r = client.put("/api/v1/admin/settings/security.session_idle_minutes",
                   json={"value": 20, "reason": REASON, "otp": "123456"})
    assert r.status_code == 403
    err = r.json()["error"]
    assert err["code"] == "step_up_unavailable"
    assert "двухфакторную" in err["message"]


def test_admin_toggles_mfa_required_with_step_up(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    # Ikki admin: SeedUser.next_code() bir TOTP oynasida ikkitadan ortiq kod bera olmaydi.
    path = f"/api/v1/admin/settings/{KEY}"
    first, second = make_user("admin"), make_user("admin")
    login(client, first)
    assert client.put(path, json={"value": True, "reason": REASON}).status_code == 422
    on = client.put(path, json={"value": True, "reason": REASON, "otp": first.next_code()})
    assert on.status_code == 200, on.text
    assert sysconfig.value(KEY) is True
    other = TestClient(client.app, base_url="https://testserver")
    login(other, second)
    off = other.put(path, json={"value": False, "reason": REASON, "otp": second.next_code()})
    assert off.status_code == 200, off.text
    assert sysconfig.value(KEY) is False


def _session_id(client: TestClient) -> str:
    return str(next(s["id"] for s in client.get(f"{A}/sessions").json() if s["current"]))


def _open_pending(user_id: int) -> tuple[int, bool]:
    with get_engine("app").connect() as conn:
        row = conn.execute(text(
            "SELECT count(*), bool_or(pending_secret_enc IS NOT NULL) FROM core.mfa_challenges "
            "WHERE user_id = :u AND used_at IS NULL"), {"u": user_id}).one()
    return int(row[0]), bool(row[1])


@pytest.mark.parametrize("forged", ["session:{sid}", "{sid}", "mfa-session:{sid}"])
def test_forged_session_key_cannot_reach_session_challenge_via_token_endpoints(
    client: TestClient, make_user: Callable[..., SeedUser], forged: str
) -> None:
    """r2 C1: cookie'siz hujumchi sessiya id'sidan token yasab, begin ochgan challenge'ni
    eski enroll/start + confirm orqali ololmaydi."""
    user = make_user("rukovodstvo", totp=False)
    _as_user(client, user)
    secret = _begin(client, user).json()["secret"]
    token = forged.format(sid=_session_id(client))
    attacker = TestClient(client.app, base_url="https://testserver")
    for path, body in (("start", {}), ("confirm", {"code": pyotp.TOTP(secret).now()})):
        r = attacker.post(f"{A}/2fa/enroll/{path}", json={"mfa_token": token, **body})
        assert r.status_code in (401, 422), (path, r.text)
    assert SESSION_COOKIE not in attacker.cookies
    assert _open_pending(user.id) == (1, True)  # qurbonning challenge'i daxlsiz
    done = client.post(f"{A}/2fa/enroll/finish", json={"code": pyotp.TOTP(secret).now()})
    assert done.status_code == 200, done.text  # qurbonning o'z secret'i hamon ishlaydi


def test_challenge_key_spaces_are_disjoint() -> None:
    import uuid

    from app.auth import service
    sid = uuid.uuid4()
    assert service._session_challenge_hmac(sid) != service._challenge_hmac(f"session:{sid}")
    assert service._session_challenge_hmac(sid) != service._challenge_hmac(str(sid))


def test_mfa_token_shape_is_strict(client: TestClient) -> None:
    for bad in ("session:" + "a" * 36, "a" * 42, "a" * 44, "a" * 42 + "!", "a" * 20):
        r = client.post(f"{A}/2fa/enroll/start", json={"mfa_token": bad})
        assert r.status_code == 422, bad
    r = client.post(f"{A}/2fa/enroll/start", json={"mfa_token": "a" * 43})
    assert r.status_code == 401  # shakl to'g'ri, lekin noma'lum token
