from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, update

from app.auth.context import CSRF_COOKIE, CSRF_HEADER
from app.auth.models import User
from app.core.db import get_engine, new_session
from app.main import create_app
from tests.helpers import DEFAULT_PASSWORD, SeedUser, login

NEW_PASSWORD = "Yangi-Mustahkam-77#"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


def _login_step(client: TestClient, username: str, password: str = DEFAULT_PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def _audit_actions(user_id: int) -> list[str]:
    with get_engine("app").connect() as conn:
        return list(
            conn.execute(
                text("SELECT action FROM core.audit_log WHERE user_id = :u ORDER BY id"),
                {"u": user_id},
            ).scalars()
        )


def test_unknown_user_is_generic_401(client: TestClient) -> None:
    r = _login_step(client, "no_such_user")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_full_login_sets_hardened_cookies(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("economist_filiala", branch_ids=(4,))
    r = _login_step(client, user.username)
    assert r.status_code == 200 and r.json()["next"] == "mfa_verify"
    r = client.post(
        "/api/v1/auth/2fa/verify",
        json={"mfa_token": r.json()["mfa_token"], "code": user.next_code()},
    )
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("__Host-ugk_session="))
    for attr in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert attr.lower() in session_cookie.lower()
    assert any(c.startswith("__Host-ugk_csrf=") for c in cookies)
    body = r.json()
    assert body["username"] == user.username
    assert body["branch_ids"] == [4]
    assert "section:kazna:view" in body["permissions"]
    assert _audit_actions(user.id)[-2:] == ["auth.password.ok", "auth.login.ok"]


def test_login_username_is_normalized(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    r = _login_step(client, f"  {user.username.upper()} ")
    assert r.status_code == 200


def test_lockout_after_five_failures(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    for _ in range(5):
        assert _login_step(client, user.username, "Wrong-Password-1!").status_code == 401
    assert _login_step(client, user.username).status_code == 401  # to'g'ri parol ham rad
    with new_session() as s:
        s.execute(
            update(User)
            .where(User.id == user.id)
            .values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        s.commit()
    assert _login_step(client, user.username).status_code == 200


def test_inactive_user_cannot_login(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    with new_session() as s:
        s.execute(update(User).where(User.id == user.id).values(is_active=False))
        s.commit()
    assert _login_step(client, user.username).json()["error"]["code"] == "invalid_credentials"


def test_challenge_dies_after_five_wrong_codes(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    token = _login_step(client, user.username).json()["mfa_token"]
    for _ in range(5):
        r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": "000000"})
        assert r.json()["error"]["code"] == "invalid_mfa_code"
    r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": user.next_code()})
    assert r.json()["error"]["code"] == "mfa_expired"


def test_totp_code_cannot_be_replayed(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    code = user.next_code()
    t1 = _login_step(client, user.username).json()["mfa_token"]
    r1 = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": t1, "code": code})
    assert r1.status_code == 200
    t2 = _login_step(client, user.username).json()["mfa_token"]
    r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": t2, "code": code})
    assert r.json()["error"]["code"] == "invalid_mfa_code"


def test_enroll_flow_and_backup_codes(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user(totp=False)
    r = _login_step(client, user.username)
    assert r.json()["next"] == "mfa_enroll"
    token = r.json()["mfa_token"]
    # verify-turdagi endpoint enroll tokenini qabul qilmaydi
    wrong_kind = client.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": "123456"}
    )
    assert wrong_kind.json()["error"]["code"] == "mfa_expired"
    start = client.post("/api/v1/auth/2fa/enroll/start", json={"mfa_token": token}).json()
    assert start["otpauth_uri"].startswith("otpauth://totp/UGEKAZNA:")
    assert start["qr_svg_data_uri"].startswith("data:image/svg+xml")
    otp = pyotp.TOTP(start["secret"])
    bad = client.post(
        "/api/v1/auth/2fa/enroll/confirm", json={"mfa_token": token, "code": "000000"}
    )
    assert bad.json()["error"]["code"] == "invalid_mfa_code"
    ok = client.post(
        "/api/v1/auth/2fa/enroll/confirm", json={"mfa_token": token, "code": otp.now()}
    )
    assert ok.status_code == 200
    codes = ok.json()["backup_codes"]
    assert len(codes) == 10
    assert "auth.mfa.enrolled" in _audit_actions(user.id)

    # Endi login verify'ga olib boradi; zaxira kod bir marta ishlaydi.
    fresh = TestClient(client.app, base_url="https://testserver")
    t = _login_step(fresh, user.username).json()
    assert t["next"] == "mfa_verify"
    r_used = fresh.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": t["mfa_token"], "code": codes[0].lower()}
    )
    assert r_used.status_code == 200
    t = _login_step(fresh, user.username).json()
    r_replay = fresh.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": t["mfa_token"], "code": codes[0]}
    )
    assert r_replay.status_code == 401


def test_me_and_logout(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    login(client, user)
    assert client.get("/api/v1/auth/me").json()["username"] == user.username
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_forced_password_change(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user(must_change=True)
    login(client, user)
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is True
    sessions_r = client.get("/api/v1/auth/sessions")
    assert sessions_r.json()["error"]["code"] == "password_change_required"

    weak = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "short"},
    )
    assert weak.status_code == 422
    assert "password_too_short" in weak.json()["error"]["params"]["problems"]

    wrong = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "Nope-Nope-123!", "new_password": NEW_PASSWORD},
    )
    assert wrong.json()["error"]["code"] == "invalid_current_password"

    same = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
    )
    assert same.json()["error"]["params"]["problems"] == ["password_reused"]

    other = TestClient(client.app, base_url="https://testserver")
    login(other, user)
    ok = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert ok.status_code == 204
    assert client.get("/api/v1/auth/sessions").status_code == 200  # joriy sessiya tirik
    assert other.get("/api/v1/auth/me").status_code == 401  # boshqasi bekor
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is False


def test_sessions_list_and_revoke(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    other = TestClient(client.app, base_url="https://testserver")
    login(other, user)
    login(client, user)
    listed = client.get("/api/v1/auth/sessions").json()
    assert len(listed) >= 2
    current = [s for s in listed if s["current"]]
    assert len(current) == 1 and current[0]["ip"] == "testclient"
    victim = next(s for s in listed if not s["current"])
    assert client.delete(f"/api/v1/auth/sessions/{victim['id']}").status_code == 204
    assert other.get("/api/v1/auth/me").status_code == 401


def test_cannot_revoke_foreign_session(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    a, b = make_user(), make_user()
    other = TestClient(client.app, base_url="https://testserver")
    login(other, b)
    b_session = other.get("/api/v1/auth/sessions").json()[0]["id"]
    login(client, a)
    assert client.delete(f"/api/v1/auth/sessions/{b_session}").status_code == 404


def test_csrf_header_required_for_logout(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user())
    del client.headers[CSRF_HEADER]
    assert client.post("/api/v1/auth/logout").status_code == 403
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    assert client.post("/api/v1/auth/logout").status_code == 204
