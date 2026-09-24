import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.admin import service as admin_service
from app.auth.context import AuthContext
from app.auth.models import Position, Role, User
from app.core.db import get_engine, new_session
from app.core.errors import ConflictError
from app.core.request_meta import ClientMeta
from app.main import create_app
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


def _position_id(code: str) -> int:
    with new_session() as s:
        return s.execute(select(Position.id).where(Position.code == code)).scalar_one()


def _new_username() -> str:
    return f"new.{uuid.uuid4().hex[:8]}"


def test_non_admin_forbidden(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("rukovodstvo"))
    assert client.get("/api/v1/admin/users").status_code == 403


@pytest.mark.usefixtures("admin")
def test_create_user_and_first_login_requires_enroll(client: TestClient) -> None:
    username = _new_username()
    r = client.post("/api/v1/admin/users", json={
        "username": f"  {username.upper()} ", "full_name": "Иванов И.И.",
        "position_id": _position_id("spec_kazna")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["username"] == username
    assert body["user"]["role_code"] == "spec_kazna"
    fresh = TestClient(client.app, base_url="https://testserver")
    step = fresh.post(
        "/api/v1/auth/login",
        json={"username": username, "password": body["temporary_password"]},
    )
    assert step.json()["next"] == "mfa_enroll"
    with get_engine("app").connect() as conn:
        actions = conn.execute(text(
            "SELECT action FROM core.audit_log WHERE object_type = 'user' AND object_id = :i"),
            {"i": str(body["user"]["id"])}).scalars().all()
    assert "admin.user.created" in actions


@pytest.mark.usefixtures("admin")
def test_duplicate_username_case_insensitive(client: TestClient) -> None:
    username = _new_username()
    payload = {"username": username, "full_name": "A", "position_id": _position_id("rukovodstvo")}
    assert client.post("/api/v1/admin/users", json=payload).status_code == 201
    payload["username"] = username.upper()
    r = client.post("/api/v1/admin/users", json=payload)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "username_taken"


@pytest.mark.usefixtures("admin")
def test_invalid_username_rejected(client: TestClient) -> None:
    r = client.post("/api/v1/admin/users", json={
        "username": "bad name!", "full_name": "A", "position_id": _position_id("rukovodstvo")})
    assert r.status_code == 422


def test_block_revokes_sessions(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    victim = make_user("rukovodstvo")
    victim_client = TestClient(client.app, base_url="https://testserver")
    login(victim_client, victim)
    r = client.post(f"/api/v1/admin/users/{victim.id}/block")
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert victim_client.get("/api/v1/auth/me").status_code == 401
    step = victim_client.post(
        "/api/v1/auth/login", json={"username": victim.username, "password": victim.password}
    )
    assert step.status_code == 401
    assert client.post(f"/api/v1/admin/users/{victim.id}/unblock").json()["is_active"] is True


def test_cannot_block_self(client: TestClient, admin: SeedUser) -> None:
    r = client.post(f"/api/v1/admin/users/{admin.id}/block")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "cannot_modify_self"


def test_last_admin_is_protected(db: Session, make_user: Callable[..., SeedUser]) -> None:
    actor_user, target = make_user("admin"), make_user("admin")
    db.execute(
        update(User).where(User.id.not_in([actor_user.id, target.id])).values(is_active=False)
    )
    actor = AuthContext(user_id=actor_user.id, username=actor_user.username, full_name="A",
                        role_code="admin", permissions=frozenset({"admin:users"}), branch_ids=None,
                        session_id=uuid.uuid4())
    meta = ClientMeta(ip=None, ua=None, request_id=None)
    db.execute(update(User).where(User.id == actor_user.id).values(is_active=False))
    with pytest.raises(ConflictError) as exc:
        admin_service.set_active(db, actor, target.id, False, meta)
    assert exc.value.code == "last_admin"


def test_reset_password_and_2fa(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    victim = make_user("rukovodstvo")
    reset = client.post(f"/api/v1/admin/users/{victim.id}/reset-password")
    temp = reset.json()["temporary_password"]
    assert client.post(f"/api/v1/admin/users/{victim.id}/reset-2fa").status_code == 204
    fresh = TestClient(client.app, base_url="https://testserver")
    old_login = fresh.post(
        "/api/v1/auth/login", json={"username": victim.username, "password": victim.password}
    )
    assert old_login.status_code == 401
    step = fresh.post("/api/v1/auth/login", json={"username": victim.username, "password": temp})
    assert step.json()["next"] == "mfa_enroll"


def test_reset_2fa_invalidates_open_challenge(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    """NEW: reset-2fa o'chirilishi kerak bo'lgan ochiq MFA challenge'ni ham bekor qiladi —
    parol qadamidan hosil bo'lgan `mfa_token` reset-2fa'dan keyin ishlamasligi kerak."""
    victim = make_user("rukovodstvo")
    fresh = TestClient(client.app, base_url="https://testserver")
    step = fresh.post(
        "/api/v1/auth/login", json={"username": victim.username, "password": victim.password}
    )
    assert step.status_code == 200 and step.json()["next"] == "mfa_verify"
    mfa_token = step.json()["mfa_token"]
    assert client.post(f"/api/v1/admin/users/{victim.id}/reset-2fa").status_code == 204
    verify = fresh.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": mfa_token, "code": victim.next_code()}
    )
    assert verify.status_code == 401
    assert verify.json()["error"]["code"] == "mfa_expired"


def test_change_position_revokes_sessions(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    victim = make_user("rukovodstvo")
    victim_client = TestClient(client.app, base_url="https://testserver")
    login(victim_client, victim)
    r = client.patch(
        f"/api/v1/admin/users/{victim.id}", json={"position_id": _position_id("spec_kazna")}
    )
    assert r.status_code == 200 and r.json()["role_code"] == "spec_kazna"
    assert victim_client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.usefixtures("admin")
def test_roles_crud_and_admin_protection(client: TestClient) -> None:
    code = f"r_{uuid.uuid4().hex[:6]}"
    r = client.post("/api/v1/admin/roles", json={
        "code": code, "name": "Служба закупок", "scope_all": True,
        "permissions": ["section:obzor:view", "section:zakupki:view"]})
    assert r.status_code == 201
    role_id = r.json()["id"]
    assert client.post("/api/v1/admin/roles", json={
        "code": f"x_{uuid.uuid4().hex[:6]}", "name": "X", "scope_all": True,
        "permissions": ["no:such"]}).json()["error"]["code"] == "unknown_permission"
    upd = client.patch(
        f"/api/v1/admin/roles/{role_id}", json={"permissions": ["section:obzor:view"]}
    )
    assert upd.json()["permissions"] == ["section:obzor:view"]
    roles = client.get("/api/v1/admin/roles").json()
    admin_role = next(x for x in roles if x["code"] == "admin")
    r = client.patch(
        f"/api/v1/admin/roles/{admin_role['id']}", json={"permissions": ["section:obzor:view"]}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "admin_role_protected"


@pytest.mark.usefixtures("admin")
def test_positions_with_branches(client: TestClient) -> None:
    with new_session() as s:
        econ_id = s.execute(select(Role.id).where(Role.code == "economist_filiala")).scalar_one()
    code = f"econ_{uuid.uuid4().hex[:6]}"
    r = client.post("/api/v1/admin/positions", json={
        "code": code, "name": "Экономист Чарвакской ГЭС", "role_id": econ_id, "branch_ids": [2, 1]})
    assert r.status_code == 201
    assert r.json()["branch_ids"] == [1, 2]
    pid = r.json()["id"]
    r = client.patch(f"/api/v1/admin/positions/{pid}", json={"branch_ids": [5]})
    assert r.json()["branch_ids"] == [5]
    assert any(p["code"] == code for p in client.get("/api/v1/admin/positions").json())


@pytest.mark.usefixtures("admin")
def test_permissions_and_user_search(client: TestClient) -> None:
    perms = client.get("/api/v1/admin/permissions").json()
    assert {"code": "audit:read", "description": "Просмотр журнала аудита"} in perms
    page = client.get("/api/v1/admin/users", params={"q": "u", "page_size": 5}).json()
    assert page["page_size"] == 5 and len(page["items"]) <= 5 and page["total"] >= 1
    assert client.get("/api/v1/admin/users", params={"page_size": 501}).status_code == 422
