from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text, update

from app.auth import context as context_module
from app.auth import sessions
from app.auth.context import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, Ctx, require_perm
from app.auth.models import Position, User, UserSession
from app.auth.permissions import Perm
from app.core.db import DB, new_session
from app.main import create_app
from tests.helpers import SeedUser, issue_session, use_session


def _app() -> FastAPI:
    app = create_app()

    @app.get("/api/v1/_probe")
    def probe(ctx: Ctx, db: DB) -> dict[str, object]:
        return {
            "user": ctx.username,
            "branches": db.execute(
                text("SELECT current_setting('app.branch_ids', true)")
            ).scalar_one(),
            "all": db.execute(
                text("SELECT current_setting('app.scope_all', true)")
            ).scalar_one(),
        }

    @app.post("/api/v1/_probe")
    def probe_post(ctx: Ctx) -> dict[str, bool]:
        return {"ok": True}

    @app.put("/api/v1/_probe")
    def probe_put(ctx: Ctx) -> dict[str, bool]:
        return {"ok": True}

    @app.patch("/api/v1/_probe")
    def probe_patch(ctx: Ctx) -> dict[str, bool]:
        return {"ok": True}

    @app.delete("/api/v1/_probe")
    def probe_delete(ctx: Ctx) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/_admin", dependencies=[Depends(require_perm(Perm.ADMIN_USERS))])
    def admin_only() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
def client() -> TestClient:
    with TestClient(_app(), base_url="https://testserver") as c:
        yield c


def _set(session_id: object, **values: object) -> None:
    with new_session() as s:
        s.execute(update(UserSession).where(UserSession.id == session_id).values(**values))
        s.commit()


def test_no_cookie_is_401(client: TestClient) -> None:
    r = client.get("/api/v1/_probe")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


def test_valid_session_and_rls_for_global_user(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("admin")
    use_session(client, *issue_session(user.id)[:2])
    r = client.get("/api/v1/_probe")
    assert r.status_code == 200
    assert r.json() == {"user": user.username, "branches": "{}", "all": "on"}


def test_branch_user_gets_own_branches(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("economist_filiala", branch_ids=(3, 7))
    use_session(client, *issue_session(user.id)[:2])
    assert client.get("/api/v1/_probe").json()["branches"] == "{3,7}"
    assert client.get("/api/v1/_probe").json()["all"] == "off"


def test_garbage_token_is_401(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "garbage")
    assert client.get("/api/v1/_probe").json()["error"]["code"] == "session_expired"


@pytest.mark.parametrize("field", ["idle_expires_at", "absolute_expires_at", "revoked_at"])
def test_expired_or_revoked_session_is_401(
    client: TestClient, make_user: Callable[..., SeedUser], field: str
) -> None:
    user = make_user()
    token, csrf, sid = issue_session(user.id)
    _set(sid, **{field: datetime.now(UTC) - timedelta(seconds=1)})
    use_session(client, token, csrf)
    assert client.get("/api/v1/_probe").status_code == 401


def test_blocked_user_session_rejected(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    use_session(client, *issue_session(user.id)[:2])
    assert client.get("/api/v1/_probe").status_code == 200
    with new_session() as s:
        s.execute(update(User).where(User.id == user.id).values(is_active=False))
        s.commit()
    assert client.get("/api/v1/_probe").status_code == 401


def test_csrf_required_for_unsafe_methods(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    token, csrf, _ = issue_session(user.id)
    use_session(client, token, csrf)
    assert client.post("/api/v1/_probe").status_code == 200
    client.headers["X-CSRF-Token"] = "wrong"
    r = client.post("/api/v1/_probe")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_permission_required(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    use_session(client, *issue_session(make_user("rukovodstvo").id)[:2])
    assert client.get("/api/v1/_admin").status_code == 403
    use_session(client, *issue_session(make_user("admin").id)[:2])
    assert client.get("/api/v1/_admin").status_code == 200


def test_must_change_password_blocks_other_routes(
    client: TestClient, make_user: Callable[..., SeedUser], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = make_user(must_change=True)
    use_session(client, *issue_session(user.id)[:2])
    r = client.get("/api/v1/_probe")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "password_change_required"
    monkeypatch.setattr(context_module, "PASSWORD_CHANGE_ALLOWED", frozenset({"/api/v1/_probe"}))
    assert client.get("/api/v1/_probe").status_code == 200


def test_expired_password_counts_as_must_change(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    with new_session() as s:
        s.execute(
            update(User).where(User.id == user.id)
            .values(password_changed_at=datetime.now(UTC) - timedelta(days=91))
        )
        s.commit()
    use_session(client, *issue_session(user.id)[:2])
    assert client.get("/api/v1/_probe").json()["error"]["code"] == "password_change_required"


def test_session_slides_idle_expiry(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    token, csrf, sid = issue_session(user.id)
    old = datetime.now(UTC) - timedelta(minutes=5)
    _set(sid, last_seen_at=old, idle_expires_at=old + timedelta(minutes=30))
    use_session(client, token, csrf)
    assert client.get("/api/v1/_probe").status_code == 200
    with new_session() as s:
        row = s.get(UserSession, sid)
        assert row is not None
        assert row.last_seen_at > old + timedelta(minutes=4)
        assert row.idle_expires_at > datetime.now(UTC) + timedelta(minutes=29)


def test_ua_summary() -> None:
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
    assert sessions.ua_summary(ua) == "Chrome · Windows"
    assert sessions.ua_summary(None) == "—"


def test_session_ip_is_encrypted(make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    _, _, sid = issue_session(user.id)
    with new_session() as s:
        row = s.get(UserSession, sid)
        assert row is not None and row.ip_enc is not None
        assert b"10.0.0.1" not in row.ip_enc


def test_csrf_non_ascii_header_is_403_not_500(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """I1: `hmac.compare_digest` on non-ASCII str would raise TypeError -> 500.

    httpx's `Headers.__setitem__` only accepts ASCII `str` values, so the non-ASCII
    header is sent as raw bytes (matching what the ASGI server hands FastAPI for a
    real, non-ASCII wire header) rather than mutating `client.headers`.
    """
    user = make_user()
    token, csrf, _ = issue_session(user.id)
    use_session(client, token, csrf)
    r = client.post(
        "/api/v1/_probe", headers={CSRF_HEADER.encode(): "é".encode()}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_csrf_missing_header_is_403(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    token, csrf, _ = issue_session(user.id)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf)
    r = client.post("/api/v1/_probe")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_csrf_missing_cookie_with_header_is_403(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    token, csrf, _ = issue_session(user.id)
    client.cookies.set(SESSION_COOKIE, token)
    client.headers[CSRF_HEADER] = csrf
    r = client.post("/api/v1/_probe")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_csrf_unrelated_matching_pair_is_403(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """M1: cookie == header alone is not enough; must match HMAC(pepper, csrf, token)."""
    user = make_user()
    token, _, _ = issue_session(user.id)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, "unrelated-but-matching-value")
    client.headers[CSRF_HEADER] = "unrelated-but-matching-value"
    r = client.post("/api/v1/_probe")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_csrf_required_for_put_patch_delete(
    client: TestClient, make_user: Callable[..., SeedUser], method: str
) -> None:
    """M2: CSRF is required for every method outside {GET, HEAD, OPTIONS}."""
    user = make_user()
    token, csrf, _ = issue_session(user.id)
    use_session(client, token, csrf)
    assert getattr(client, method)("/api/v1/_probe").status_code == 200
    client.headers[CSRF_HEADER] = "wrong"
    r = getattr(client, method)("/api/v1/_probe")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_slide_never_exceeds_absolute_expiry(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    token, csrf, sid = issue_session(user.id)
    absolute = datetime.now(UTC) + timedelta(minutes=2)
    old = datetime.now(UTC) - timedelta(minutes=5)
    _set(sid, last_seen_at=old, absolute_expires_at=absolute, idle_expires_at=absolute)
    use_session(client, token, csrf)
    assert client.get("/api/v1/_probe").status_code == 200
    with new_session() as s:
        row = s.get(UserSession, sid)
        assert row is not None
        assert row.idle_expires_at == absolute


def test_inactive_position_has_no_scope(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("economist_filiala", branch_ids=(3,))
    use_session(client, *issue_session(user.id)[:2])
    with new_session() as s:
        row = s.get(User, user.id)
        assert row is not None
        s.execute(update(Position).where(Position.id == row.position_id).values(is_active=False))
        s.commit()
    r = client.get("/api/v1/_probe")
    assert r.json()["branches"] == "{}"
    assert r.json()["all"] == "off"
    assert client.get("/api/v1/_admin").status_code == 403


def test_require_perm_exposes_required_perms() -> None:
    dep = require_perm(Perm.ADMIN_USERS, Perm.AUDIT_READ)
    expected = frozenset({Perm.ADMIN_USERS.value, Perm.AUDIT_READ.value})
    assert dep.required_perms == expected  # type: ignore[attr-defined]


def test_require_perm_without_args_raises_at_definition_time() -> None:
    with pytest.raises(ValueError):
        require_perm()


def test_stored_token_hmac_matches_and_never_the_raw_token(
    make_user: Callable[..., SeedUser],
) -> None:
    user = make_user()
    token, _, sid = issue_session(user.id)
    with new_session() as s:
        row = s.get(UserSession, sid)
        assert row is not None
        assert row.token_hmac == sessions.token_hmac(token)
        assert row.token_hmac != token.encode("utf-8")
        assert token.encode("utf-8") not in row.token_hmac
