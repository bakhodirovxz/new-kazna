from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import passwords, sessions
from app.auth.models import User, UserSession
from app.core import ratelimit, sysconfig
from app.core.config import Settings
from app.core.db import get_engine, new_session
from app.main import create_app
from tests.helpers import SeedUser, login

Put = Callable[[str, object], None]


def _client() -> TestClient:
    return TestClient(create_app(), base_url="https://testserver")


def test_session_timeouts_follow_panel(setting: Put, make_user: Callable[..., SeedUser]) -> None:
    setting("security.session_idle_minutes", 10)
    setting("security.session_absolute_hours", 2)
    user = make_user("admin")
    now = datetime.now(UTC)
    with new_session() as s:
        new = sessions.create(s, user.id, None, "pytest", now)
        row = s.get(UserSession, new.id)
        assert row is not None
        assert row.idle_expires_at == now + timedelta(minutes=10)
        assert row.absolute_expires_at == now + timedelta(hours=2)
        s.rollback()


def test_weaker_panel_value_is_ignored(setting: Put) -> None:
    setting("security.session_idle_minutes", 45)
    setting("security.login_max_failures", 50)
    assert sysconfig.value("security.session_idle_minutes") == 30
    assert sysconfig.value("security.login_max_failures") == 5


def test_lockout_follows_panel(setting: Put, make_user: Callable[..., SeedUser]) -> None:
    setting("security.login_max_failures", 3)
    setting("security.login_lockout_minutes", 60)
    user = make_user("admin")
    with _client() as client:
        for _ in range(3):
            r = client.post("/api/v1/auth/login",
                            json={"username": user.username, "password": "Wrong-Passw0rd!"})
            assert r.status_code == 401
    with new_session() as s:
        locked_until = s.get(User, user.id).locked_until  # type: ignore[union-attr]
    assert locked_until is not None
    assert locked_until - datetime.now(UTC) > timedelta(minutes=55)


def test_password_policy_follows_panel(setting: Put, make_user: Callable[..., SeedUser]) -> None:
    setting("security.password_min_length", 14)
    setting("security.password_history", 8)
    assert "password_too_short" in passwords.policy_problems("Qwz-Lmn-8472x", username="ivan")
    assert "password_too_short" not in passwords.policy_problems("Qwz-Lmn-8472xy",
                                                                 username="ivan")
    assert passwords.history_depth() == 8
    with _client() as client:
        login(client, make_user("admin"))
        assert client.get("/api/v1/auth/me").json()["password_min_length"] == 14


def test_password_max_age_follows_panel(setting: Put, make_user: Callable[..., SeedUser]) -> None:
    user = make_user("admin")
    with get_engine("app").begin() as conn:
        conn.execute(text("UPDATE core.users SET password_changed_at = now() - interval "
                          "'40 days' WHERE id = :i"), {"i": user.id})
    with _client() as client:
        login(client, user)
        assert client.get("/api/v1/auth/me").json()["must_change_password"] is False
        setting("security.password_max_age_days", 30)
        assert client.get("/api/v1/auth/me").json()["must_change_password"] is True


def test_login_rate_limit_follows_panel(setting: Put) -> None:
    setting("ratelimit.login_per_min", 3)
    assert ratelimit.login_per_ip() == ratelimit.Limit(events=3, window=60)
    with _client() as client:
        codes = [client.post("/api/v1/auth/login",
                             json={"username": "nobody_x", "password": "x"}).status_code
                 for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_removed_env_fields_are_ignored() -> None:
    settings = Settings(session_idle_minutes=120, login_max_failures=99)  # type: ignore[call-arg]
    assert not hasattr(settings, "session_idle_minutes")
    assert not hasattr(settings, "login_max_failures")
