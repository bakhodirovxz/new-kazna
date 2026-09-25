import uuid
from collections.abc import Callable, Iterable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.admin import service as admin_service
from app.admin.schemas import PositionUpdate, UserUpdate
from app.auth.context import AuthContext
from app.auth.models import Position, Role, RolePermission, User
from app.auth.permissions import PERMISSIONS
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


def _role_id(code: str) -> int:
    with new_session() as s:
        return s.execute(select(Role.id).where(Role.code == code)).scalar_one()


def _user_position_id(user_id: int) -> int:
    with new_session() as s:
        return s.execute(select(User.position_id).where(User.id == user_id)).scalar_one()


def _new_username() -> str:
    return f"new.{uuid.uuid4().hex[:8]}"


def _make_role(perms: Iterable[str], *, scope_all: bool = True) -> str:
    """Faqat berilgan ruxsatlarga ega maxsus rol yaratadi — I3/R2-3 (imtiyoz/doira
    eskalatsiyasi) testlari uchun cheklangan aktyorlar tayyorlashda ishlatiladi. `scope_all`
    `False` bo'lsa, `make_user(role_code, branch_ids=(...))` bilan birga ishlatilib, actor
    filial doirasi bilan cheklangan (`AuthContext.branch_ids is not None`) bo'ladi."""
    code = f"custom_{uuid.uuid4().hex[:8]}"
    with new_session() as s:
        role = Role(code=code, name="Custom", scope_all=scope_all, is_system=False)
        s.add(role)
        s.flush()
        for perm in perms:
            s.add(RolePermission(role_id=role.id, permission_code=perm))
        s.commit()
    return code


def _role_perms_for_code(role_code: str) -> frozenset[str]:
    with new_session() as s:
        role_id = s.execute(select(Role.id).where(Role.code == role_code)).scalar_one()
        return frozenset(
            s.execute(
                select(RolePermission.permission_code).where(RolePermission.role_id == role_id)
            ).scalars()
        )


def _full_admin_ctx(user_id: int, username: str) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        username=username,
        full_name="A",
        role_code="admin",
        permissions=frozenset(PERMISSIONS),
        branch_ids=None,
        session_id=uuid.uuid4(),
    )


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


# Minor (fix r2): kod-nuqtalar `chr()` orqali quriladi — manba fayl ichida bevosita
# escape yozib qo'yish ko'rinmas belgilarning o'zini fayl ichida qoldirib ketishi mumkin
# edi (aynan shu narsa fix r1'da sodir bo'lgan va fix r2'da tuzatilgan, qarang schemas.py).
_REJECTED_CODEPOINTS = (
    0x00,  # NUL
    0x7F,  # DEL
    0x9F,  # C1 boshqaruv (U+0080-U+009F)
    0x202E,  # RLO (bidi almashtirish)
    0x2066,  # LRI (bidi izolat)
    0x200E,  # LRM
    0x200F,  # RLM
    0x061C,  # ALM
    0x2028,  # satr ajratgich
    0x2029,  # abzats ajratgich
)


@pytest.mark.usefixtures("admin")
def test_control_chars_in_full_name_rejected(client: TestClient) -> None:
    """Minor (fix r1, kengaytirilgan r2): boshqaruv, C1 va bidi/yo'naltirish belgilari
    `full_name`da 422 bilan rad etiladi."""
    for codepoint in _REJECTED_CODEPOINTS:
        payload = {
            "username": _new_username(), "full_name": f"A{chr(codepoint)}B",
            "position_id": _position_id("rukovodstvo"),
        }
        r = client.post("/api/v1/admin/users", json=payload)
        assert r.status_code == 422, f"U+{codepoint:04X} rad etilmadi: {r.text}"


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
    # R2-2 fix: actor to'liq admin ruxsatlariga ega bo'lishi kerak — aks holda R2-2'ning
    # "target CURRENT permissions ⊆ actor.permissions" tekshiruvi (target ham "admin" roli,
    # ya'ni BARCHA ruxsatlarga ega) `last_admin`ga yetmasdan turib `privilege_escalation`
    # bilan yiqilardi.
    actor = _full_admin_ctx(actor_user.id, actor_user.username)
    meta = ClientMeta(ip=None, ua=None, request_id=None)
    db.execute(update(User).where(User.id == actor_user.id).values(is_active=False))
    with pytest.raises(ConflictError) as exc:
        admin_service.set_active(db, actor, target.id, False, meta)
    assert exc.value.code == "last_admin"


def test_last_admin_requires_full_admin_guarantee(
    db: Session, make_user: Callable[..., SeedUser]
) -> None:
    """I2: faqat `admin:users`ga ega (lekin `admin:roles`siz) rol "admin" hisoblanmaydi —
    invariant ADMIN_GUARANTEED'ning BARCHASINI talab qiladi."""
    role_code = _make_role({"admin:users"})
    partial = make_user(role_code)
    db.execute(update(User).where(User.id != partial.id).values(is_active=False))
    with pytest.raises(ConflictError) as exc:
        admin_service.assert_admin_remains(db)
    assert exc.value.code == "last_admin"


def test_last_admin_via_position_change(db: Session, make_user: Callable[..., SeedUser]) -> None:
    actor_user, target = make_user("admin"), make_user("admin")
    db.execute(
        update(User).where(User.id.not_in([actor_user.id, target.id])).values(is_active=False)
    )
    db.execute(update(User).where(User.id == actor_user.id).values(is_active=False))
    actor = _full_admin_ctx(actor_user.id, actor_user.username)
    meta = ClientMeta(ip=None, ua=None, request_id=None)
    with pytest.raises(ConflictError) as exc:
        admin_service.update_user(
            db, actor, target.id, UserUpdate(position_id=_position_id("rukovodstvo")), meta
        )
    assert exc.value.code == "last_admin"


def test_last_admin_via_position_deactivation(
    db: Session, make_user: Callable[..., SeedUser]
) -> None:
    actor_user, target = make_user("admin"), make_user("admin")
    db.execute(
        update(User).where(User.id.not_in([actor_user.id, target.id])).values(is_active=False)
    )
    db.execute(update(User).where(User.id == actor_user.id).values(is_active=False))
    actor = _full_admin_ctx(actor_user.id, actor_user.username)
    meta = ClientMeta(ip=None, ua=None, request_id=None)
    target_position_id = _user_position_id(target.id)
    with pytest.raises(ConflictError) as exc:
        admin_service.update_position(
            db, actor, target_position_id, PositionUpdate(is_active=False), meta
        )
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
    """reset-2fa o'chirilishi kerak bo'lgan ochiq MFA challenge'ni ham bekor qiladi —
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
def test_roles_crud(client: TestClient) -> None:
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


@pytest.mark.usefixtures("admin")
def test_update_role_cannot_edit_own_role(client: TestClient) -> None:
    """I3: actor (bu yerda "admin" rolidagi foydalanuvchi) o'z rolini tahrirlay olmaydi."""
    roles = client.get("/api/v1/admin/roles").json()
    admin_role = next(x for x in roles if x["code"] == "admin")
    r = client.patch(f"/api/v1/admin/roles/{admin_role['id']}", json={"name": "X"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "cannot_modify_self"


def test_admin_role_permissions_are_protected(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """I3/admin_role_protected: "admin" rolining o'zida bo'lmagan, lekin uning BARCHA
    HOZIRGI ruxsatlariga ega actor (F2 pre-check'dan o'tishi uchun) "admin" rolidan
    ADMIN_GUARANTEED ruxsatlarini olib tashlashga urinadi — `cannot_modify_self` bu yerda
    ishlamaydi (actor.role_code != "admin"), shuning uchun `admin_role_protected` chin
    sinaladi."""
    actor = make_user(_make_role(_role_perms_for_code("admin") | {"section:obzor:view"}))
    login(client, actor)
    roles = client.get("/api/v1/admin/roles").json()
    admin_role = next(x for x in roles if x["code"] == "admin")
    r = client.patch(
        f"/api/v1/admin/roles/{admin_role['id']}", json={"permissions": ["section:obzor:view"]}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "admin_role_protected"


def test_create_role_privilege_escalation_forbidden(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    actor = make_user(_make_role({"admin:roles"}))
    login(client, actor)
    r = client.post("/api/v1/admin/roles", json={
        "code": f"esc_{uuid.uuid4().hex[:6]}", "name": "Esc", "scope_all": True,
        "permissions": ["admin:users"]})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_role_privilege_escalation_forbidden(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    actor = make_user(_make_role({"admin:roles", "section:obzor:view"}))
    login(client, actor)
    created = client.post("/api/v1/admin/roles", json={
        "code": f"tgt_{uuid.uuid4().hex[:6]}", "name": "Target", "scope_all": True,
        "permissions": ["section:obzor:view"]})
    assert created.status_code == 201
    role_id = created.json()["id"]
    r = client.patch(f"/api/v1/admin/roles/{role_id}", json={"permissions": ["admin:users"]})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_create_user_privilege_escalation_forbidden(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    actor = make_user(_make_role({"admin:users"}))
    login(client, actor)
    r = client.post("/api/v1/admin/users", json={
        "username": _new_username(), "full_name": "A",
        "position_id": _position_id("rukovodstvo")})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_user_position_privilege_escalation_forbidden(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    actor = make_user(_make_role({"admin:users"}))
    login(client, actor)
    # R2-2 fix: victim'ning HOZIRGI roli bo'sh ruxsatli bo'lishi kerak — aks holda R2-2'ning
    # "target CURRENT permissions ⊆ actor.permissions" tekshiruvi shu I3 (YANGI lavozim)
    # holatidan OLDIN ishga tushib, testni R2-2'ga aylantirib qo'yardi.
    victim = make_user(_make_role(set()))
    r = client.patch(
        f"/api/v1/admin/users/{victim.id}", json={"position_id": _position_id("rukovodstvo")}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_target_user_protection_against_out_of_reach_admin(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """R2-2: faqat `admin:users`ga ega actor to'liq administrator (target)ni reset-password,
    reset-2fa yoki blok qila olmaydi — lekin O'ZIDA BOR ruxsatlar doirasidagi (bu yerda —
    bo'sh ruxsatli) target uchun bemalol ishlaydi.

    NB: topshiriqda misol sifatida "rukovodstvo" target keltirilgan, lekin haqiqatda
    "rukovodstvo" roli BARCHA bo'lim (`section:*:view`) va eksport ruxsatlariga ega
    (`ROLE_SEEDS` — `_ALL_SECTIONS | _EXPORT`), bu esa `{"admin:users"}`ning qat'iy
    natijaviy to'plami EMAS — demak, "target CURRENT permissions ⊆ actor.permissions"
    formulasi (I3'dagi bilan bir xil, allaqachon ko'rib chiqilgan semantika) bo'yicha
    "rukovodstvo" ham "reach doirasidan tashqarida" bo'lib chiqadi. Shu sabab bu yerda aniq
    bo'sh ruxsatli maxsus rol ishlatiladi — formulaning o'zi (topshiriqning so'zma-so'z
    matnidagi misol emas) qat'iy bajarilishi uchun. Bu nomuvofiqlik hisobotda alohida
    qayd etilgan."""
    actor = make_user(_make_role({"admin:users"}))
    login(client, actor)
    full_admin_target = make_user("admin")

    for r in (
        client.post(f"/api/v1/admin/users/{full_admin_target.id}/reset-password"),
        client.post(f"/api/v1/admin/users/{full_admin_target.id}/reset-2fa"),
        client.post(f"/api/v1/admin/users/{full_admin_target.id}/block"),
    ):
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "privilege_escalation"

    victim = make_user(_make_role(set()))
    assert client.post(f"/api/v1/admin/users/{victim.id}/reset-password").status_code == 200
    assert client.post(f"/api/v1/admin/users/{victim.id}/reset-2fa").status_code == 204
    assert client.post(f"/api/v1/admin/users/{victim.id}/block").status_code == 200


def test_update_user_full_name_forbidden_for_out_of_reach_target(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """R2-2: `update_user`da faqat `full_name` o'zgartirilsa ham, target'ning HOZIRGI roli
    actor'da yo'q ruxsatlarga ega bo'lsa, rad etiladi."""
    actor = make_user(_make_role({"admin:users"}))
    login(client, actor)
    full_admin_target = make_user("admin")
    r = client.patch(
        f"/api/v1/admin/users/{full_admin_target.id}", json={"full_name": "New Name"}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_create_role_scope_all_forbidden_for_branch_limited_actor(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """R2-3(a): filial doirasi bilan cheklangan actor `scope_all=True` rol yarata olmaydi."""
    actor = make_user(_make_role({"admin:roles"}, scope_all=False), branch_ids=(1,))
    login(client, actor)
    r = client.post("/api/v1/admin/roles", json={
        "code": f"scope_{uuid.uuid4().hex[:6]}", "name": "X", "scope_all": True,
        "permissions": []})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_role_scope_all_forbidden_for_branch_limited_actor(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """R2-3(a): filial doirasi bilan cheklangan actor mavjud rolni `scope_all=True`ga
    o'zgartira olmaydi."""
    actor = make_user(_make_role({"admin:roles"}, scope_all=False), branch_ids=(1,))
    login(client, actor)
    created = client.post("/api/v1/admin/roles", json={
        "code": f"tgt_{uuid.uuid4().hex[:6]}", "name": "Target", "scope_all": False,
        "permissions": []})
    assert created.status_code == 201
    role_id = created.json()["id"]
    r = client.patch(f"/api/v1/admin/roles/{role_id}", json={"scope_all": True})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_role_current_permissions_out_of_reach_forbidden(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """F2 (R2-2 mirror): faqat `admin:roles`ga ega actor "admin" rolini — uning HOZIRGI
    ruxsatlari actor'da yo'q bo'lgani uchun — hech qanday maydon (hatto faqat `name`) bo'yicha
    ham tahrirlay olmaydi. `cannot_modify_self` bu yerda ishlamaydi (actor.role_code != "admin")."""
    actor = make_user(_make_role({"admin:roles"}))
    login(client, actor)
    roles = client.get("/api/v1/admin/roles").json()
    admin_role = next(x for x in roles if x["code"] == "admin")
    r = client.patch(f"/api/v1/admin/roles/{admin_role['id']}", json={"name": "X"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_role_current_scope_all_forbidden_for_branch_limited_actor(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    """F2: filial doirasi bilan cheklangan actor HOZIRGI scope_all=True rolga umuman
    tegina olmaydi — `scope_all` maydoni PATCH so'rovida ishtirok etmasa (masalan, faqat
    `name` o'zgartirilsa) ham."""
    created = client.post("/api/v1/admin/roles", json={
        "code": f"tgt_{uuid.uuid4().hex[:6]}", "name": "Target", "scope_all": True,
        "permissions": []})
    assert created.status_code == 201
    role_id = created.json()["id"]

    limited = make_user(_make_role({"admin:roles"}, scope_all=False), branch_ids=(1,))
    limited_client = TestClient(client.app, base_url="https://testserver")
    login(limited_client, limited)
    r = limited_client.patch(f"/api/v1/admin/roles/{role_id}", json={"name": "Renamed"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_create_position_branch_escalation_forbidden(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """R2-3(b): filial doirasi bilan cheklangan actor o'z doirasidan tashqi filiallarni
    yangi lavozimga biriktira olmaydi."""
    actor = make_user(_make_role({"admin:roles"}, scope_all=False), branch_ids=(1,))
    login(client, actor)
    r = client.post("/api/v1/admin/positions", json={
        "code": f"pos_{uuid.uuid4().hex[:6]}", "name": "X",
        "role_id": _role_id("economist_filiala"), "branch_ids": [1, 2]})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_position_branch_escalation_forbidden(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    """R2-3(b): xuddi shu narsa mavjud lavozimni yangilashda ham amal qiladi. Actor'ga
    lavozimning HOZIRGI roli (`economist_filiala`) ruxsatlari ham beriladi — aks holda F2
    (R2-2 mirror) pre-check bu testdan OLDIN ishlab, uni branch-escalation emas, "HOZIRGI
    rol yetib bo'lmas" holatiga aylantirib qo'yardi."""
    created = client.post("/api/v1/admin/positions", json={
        "code": f"pos_{uuid.uuid4().hex[:6]}", "name": "X",
        "role_id": _role_id("economist_filiala"), "branch_ids": [1]})
    assert created.status_code == 201
    position_id = created.json()["id"]

    actor_perms = _role_perms_for_code("economist_filiala") | {"admin:roles"}
    limited = make_user(_make_role(actor_perms, scope_all=False), branch_ids=(1,))
    limited_client = TestClient(client.app, base_url="https://testserver")
    login(limited_client, limited)
    r = limited_client.patch(
        f"/api/v1/admin/positions/{position_id}", json={"branch_ids": [1, 3]}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_create_user_into_scope_all_position_forbidden_for_branch_limited_actor(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """R2-3(c): filial doirasi bilan cheklangan actor foydalanuvchini `scope_all` roldagi
    lavozimga joylashtira olmaydi — actor "profil_sluzhba"ning BARCHA ruxsatlariga ega
    bo'lsa ham (I3 emas, aynan doira tekshiruvi ishlashi uchun izolyatsiya qilingan)."""
    actor_perms = _role_perms_for_code("profil_sluzhba") | {"admin:users"}
    actor = make_user(_make_role(actor_perms, scope_all=False), branch_ids=(1,))
    login(client, actor)
    r = client.post("/api/v1/admin/users", json={
        "username": _new_username(), "full_name": "A",
        "position_id": _position_id("profil_sluzhba")})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_create_user_into_out_of_branch_position_forbidden(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    """R2-3(c): filial doirasi bilan cheklangan actor foydalanuvchini o'z doirasidan tashqi
    filiallarga ega (lekin scope_all bo'lmagan) lavozimga ham joylashtira olmaydi."""
    created = client.post("/api/v1/admin/positions", json={
        "code": f"pos_{uuid.uuid4().hex[:6]}", "name": "X",
        "role_id": _role_id("economist_filiala"), "branch_ids": [99]})
    assert created.status_code == 201
    position_id = created.json()["id"]

    actor_perms = _role_perms_for_code("economist_filiala") | {"admin:users"}
    actor = make_user(_make_role(actor_perms, scope_all=False), branch_ids=(1,))
    login(client, actor)
    r = client.post("/api/v1/admin/users", json={
        "username": _new_username(), "full_name": "A", "position_id": position_id})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_user_position_scope_all_forbidden_for_branch_limited_actor(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """R2-3(c): `update_user`ning lavozim o'zgartirish yo'lida ham xuddi shunday tekshiriladi."""
    actor_perms = _role_perms_for_code("profil_sluzhba") | {"admin:users"}
    actor = make_user(_make_role(actor_perms, scope_all=False), branch_ids=(1,))
    login(client, actor)
    # R2-2: victim'ning HOZIRGI roli bo'sh bo'lsin — faqat R2-3(c) (YANGI lavozim) tekshirilsin.
    victim = make_user(_make_role(set()))
    r = client.patch(
        f"/api/v1/admin/users/{victim.id}",
        json={"position_id": _position_id("profil_sluzhba")},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_position_role_privilege_escalation_forbidden(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    """Actor'ga lavozimning HOZIRGI roli (`economist_filiala`) ruxsatlari ham beriladi —
    aks holda F2 (R2-2 mirror) pre-check bu testdan OLDIN ishlab, uni "yangi rolga
    eskalatsiya" emas, "HOZIRGI rol yetib bo'lmas" holatiga aylantirib qo'yardi."""
    code = f"pos_{uuid.uuid4().hex[:6]}"
    created = client.post("/api/v1/admin/positions", json={
        "code": code, "name": "Test position", "role_id": _role_id("economist_filiala"),
        "branch_ids": []})
    assert created.status_code == 201
    position_id = created.json()["id"]

    actor_perms = _role_perms_for_code("economist_filiala") | {"admin:roles"}
    limited = make_user(_make_role(actor_perms))
    limited_client = TestClient(client.app, base_url="https://testserver")
    login(limited_client, limited)
    r = limited_client.patch(
        f"/api/v1/admin/positions/{position_id}", json={"role_id": _role_id("rukovodstvo")}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_position_current_role_out_of_reach_forbidden(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    """F2 (R2-2 mirror): faqat `admin:roles`ga ega actor "admin" rolidagi lavozimni —
    uning HOZIRGI roli orqali beriladigan ruxsatlar actor'da yo'qligi sababli — hech qanday
    maydon (hatto faqat `is_active`) bo'yicha ham o'zgartira olmaydi."""
    created = client.post("/api/v1/admin/positions", json={
        "code": f"pos_{uuid.uuid4().hex[:6]}", "name": "Admin position copy",
        "role_id": _role_id("admin"), "branch_ids": []})
    assert created.status_code == 201
    position_id = created.json()["id"]

    limited = make_user(_make_role({"admin:roles"}))
    limited_client = TestClient(client.app, base_url="https://testserver")
    login(limited_client, limited)
    r = limited_client.patch(
        f"/api/v1/admin/positions/{position_id}", json={"is_active": False}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_position_current_scope_all_forbidden_for_branch_limited_actor(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    """F2: filial doirasi bilan cheklangan actor HOZIRGI scope_all rolidagi lavozimga
    umuman tegina olmaydi — `role_id`/`branch_ids` maydonlari PATCH'da ishtirok etmasa
    (masalan, faqat `name` o'zgartirilsa) ham."""
    created = client.post("/api/v1/admin/positions", json={
        "code": f"pos_{uuid.uuid4().hex[:6]}", "name": "X",
        "role_id": _role_id("profil_sluzhba"), "branch_ids": []})
    assert created.status_code == 201
    position_id = created.json()["id"]

    actor_perms = _role_perms_for_code("profil_sluzhba") | {"admin:roles"}
    limited = make_user(_make_role(actor_perms, scope_all=False), branch_ids=(1,))
    limited_client = TestClient(client.app, base_url="https://testserver")
    login(limited_client, limited)
    r = limited_client.patch(
        f"/api/v1/admin/positions/{position_id}", json={"name": "Renamed"}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_position_new_role_id_scope_all_forbidden_for_branch_limited_actor(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    """F2: kechiktirilgan nuqson — lavozimning YANGI `role_id`si ham doira tekshiruvidan
    o'tishi kerak: filial doirasi bilan cheklangan actor lavozimni scope_all rolga
    ko'chira olmaydi, garchi HOZIRGI rol (`economist_filiala`) va filiallar uning doirasida
    bo'lsa va u yangi rolning (`profil_sluzhba`) barcha ruxsatlariga ega bo'lsa ham (I3 emas,
    aynan yangi rol uchun doira tekshiruvi ishlashi izolyatsiya qilingan)."""
    created = client.post("/api/v1/admin/positions", json={
        "code": f"pos_{uuid.uuid4().hex[:6]}", "name": "X",
        "role_id": _role_id("economist_filiala"), "branch_ids": [1]})
    assert created.status_code == 201
    position_id = created.json()["id"]

    actor_perms = (
        _role_perms_for_code("economist_filiala")
        | _role_perms_for_code("profil_sluzhba")
        | {"admin:roles"}
    )
    limited = make_user(_make_role(actor_perms, scope_all=False), branch_ids=(1,))
    limited_client = TestClient(client.app, base_url="https://testserver")
    login(limited_client, limited)
    r = limited_client.patch(
        f"/api/v1/admin/positions/{position_id}",
        json={"role_id": _role_id("profil_sluzhba")},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_update_position_cannot_modify_own_position(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    actor = make_user(_make_role({"admin:roles"}))
    login(client, actor)
    own_position_id = _user_position_id(actor.id)
    r = client.patch(f"/api/v1/admin/positions/{own_position_id}", json={"name": "New name"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "cannot_modify_self"


def test_update_position_deactivation_revokes_sessions_and_kills_challenge(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    """I4: `update_position` lavozimdagi BARCHA foydalanuvchilarning sessiyalari VA ochiq
    MFA challenge'larini bekor qiladi (nafaqat sessiyalarini, brief'dagidek)."""
    victim = make_user("rukovodstvo")
    victim_client = TestClient(client.app, base_url="https://testserver")
    login(victim_client, victim)
    fresh = TestClient(client.app, base_url="https://testserver")
    step = fresh.post(
        "/api/v1/auth/login", json={"username": victim.username, "password": victim.password}
    )
    assert step.status_code == 200
    mfa_token = step.json()["mfa_token"]

    position_id = _user_position_id(victim.id)
    r = client.patch(f"/api/v1/admin/positions/{position_id}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert victim_client.get("/api/v1/auth/me").status_code == 401
    verify = fresh.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": mfa_token, "code": victim.next_code()}
    )
    assert verify.status_code == 401
    assert verify.json()["error"]["code"] == "mfa_expired"


def test_update_position_role_change_revokes_sessions_and_kills_challenge(
    client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]
) -> None:
    victim = make_user("rukovodstvo")
    victim_client = TestClient(client.app, base_url="https://testserver")
    login(victim_client, victim)
    fresh = TestClient(client.app, base_url="https://testserver")
    step = fresh.post(
        "/api/v1/auth/login", json={"username": victim.username, "password": victim.password}
    )
    assert step.status_code == 200
    mfa_token = step.json()["mfa_token"]

    position_id = _user_position_id(victim.id)
    r = client.patch(
        f"/api/v1/admin/positions/{position_id}", json={"role_id": _role_id("spec_kazna")}
    )
    assert r.status_code == 200 and r.json()["role_code"] == "spec_kazna"
    assert victim_client.get("/api/v1/auth/me").status_code == 401
    verify = fresh.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": mfa_token, "code": victim.next_code()}
    )
    assert verify.status_code == 401
    assert verify.json()["error"]["code"] == "mfa_expired"


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


def test_escape_like_quotes_special_chars() -> None:
    assert admin_service._escape_like("50%_off\\thing") == "50\\%\\_off\\\\thing"


@pytest.mark.usefixtures("admin")
def test_search_percent_wildcard_is_escaped(client: TestClient) -> None:
    total = client.get("/api/v1/admin/users", params={"page_size": 1}).json()["total"]
    assert total >= 1
    percent = client.get("/api/v1/admin/users", params={"q": "%", "page_size": 1}).json()
    assert percent["total"] == 0


@pytest.mark.usefixtures("admin")
def test_search_underscore_wildcard_is_escaped(client: TestClient) -> None:
    username = _new_username()
    assert "_" not in username
    payload = {
        "username": username, "full_name": "NoUnderscore",
        "position_id": _position_id("rukovodstvo"),
    }
    assert client.post("/api/v1/admin/users", json=payload).status_code == 201
    results = client.get(
        "/api/v1/admin/users", params={"q": "_", "page_size": 500}
    ).json()["items"]
    assert username not in {u["username"] for u in results}


@pytest.mark.usefixtures("admin")
def test_temporary_password_not_leaked_into_audit_log(client: TestClient) -> None:
    username = _new_username()
    created = client.post("/api/v1/admin/users", json={
        "username": username, "full_name": "A", "position_id": _position_id("rukovodstvo")})
    temp_create = created.json()["temporary_password"]
    user_id = created.json()["user"]["id"]
    reset = client.post(f"/api/v1/admin/users/{user_id}/reset-password")
    temp_reset = reset.json()["temporary_password"]
    with get_engine("app").connect() as conn:
        rows = conn.execute(
            text(
                "SELECT details::text FROM core.audit_log "
                "WHERE object_type = 'user' AND object_id = :i"
            ),
            {"i": str(user_id)},
        ).scalars().all()
    blob = "\n".join(rows)
    assert temp_create not in blob
    assert temp_reset not in blob


@pytest.mark.usefixtures("admin")
def test_role_created_audit_details_contain_unmasked_role_code(client: TestClient) -> None:
    """F1: `details`dagi kalit `role_code` (`code` emas) — `logging.mask` `code` kalitini
    "sezgir" deb topib "***"ga aylantirib qo'yishi oldini oladi."""
    code = f"aud_{uuid.uuid4().hex[:6]}"
    r = client.post("/api/v1/admin/roles", json={
        "code": code, "name": "Audit Role", "scope_all": True, "permissions": []})
    assert r.status_code == 201, r.text
    role_id = r.json()["id"]
    with get_engine("app").connect() as conn:
        details = conn.execute(
            text(
                "SELECT details FROM core.audit_log "
                "WHERE object_type = 'role' AND object_id = :i"
            ),
            {"i": str(role_id)},
        ).scalar_one()
    assert details["role_code"] == code


@pytest.mark.usefixtures("admin")
def test_position_created_audit_details_contain_unmasked_position_code(
    client: TestClient,
) -> None:
    """F1: xuddi shu narsa lavozimlar uchun — `position_code` maskalanmaydi."""
    code = f"aud_{uuid.uuid4().hex[:6]}"
    r = client.post("/api/v1/admin/positions", json={
        "code": code, "name": "Audit Position",
        "role_id": _role_id("economist_filiala"), "branch_ids": []})
    assert r.status_code == 201, r.text
    position_id = r.json()["id"]
    with get_engine("app").connect() as conn:
        details = conn.execute(
            text(
                "SELECT details FROM core.audit_log "
                "WHERE object_type = 'position' AND object_id = :i"
            ),
            {"i": str(position_id)},
        ).scalar_one()
    assert details["position_code"] == code


def test_forbidden_admin_access_is_audited(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """Minor (fix r1): ruxsat yetishmasligi sababli rad etilgan admin so'rovi auditga
    `security.access_denied` sifatida yoziladi (`require_perm` dependency'sida)."""
    user = make_user("rukovodstvo")
    login(client, user)
    r = client.get("/api/v1/admin/users")
    assert r.status_code == 403
    with get_engine("app").connect() as conn:
        row = conn.execute(
            text(
                "SELECT action, result FROM core.audit_log WHERE user_id = :u "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"u": user.id},
        ).mappings().first()
    assert row is not None
    assert row["action"] == "security.access_denied"
    assert row["result"] == "denied"
