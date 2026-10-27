"""Security review I2: admin:* va data:* bitta rolda bo'lmaydi; data:* audit; step-up."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import select, text

from app.admin import service
from app.admin.schemas import PositionIn, PositionUpdate, RoleIn, RoleUpdate, UserCreate
from app.auth.models import Role
from app.auth.permissions import ROLE_SEEDS, sod_conflict
from app.auth.seed import sync_reference
from app.core.db import apply_rls, new_session
from app.core.errors import ValidationFailed
from tests.helpers import SeedUser
from tests.manual_helpers import META, audit_rows, ctx_of

MakeUser = Callable[..., SeedUser]
WRITE, APPROVE = "data:kazna:write", "data:kazna:approve"


def _role(code: str) -> str:
    return f"{code}_{uuid.uuid4().hex[:8]}"


def _call(actor, fn, *args):  # type: ignore[no-untyped-def]
    with new_session() as s:
        apply_rls(s, None)
        out = fn(s, actor, *args, META)
        s.commit()
        return out


def _new_role(actor, code: str, perms: list[str], otp: str | None = None):  # type: ignore[no-untyped-def]
    return _call(actor, service.create_role,
                 RoleIn(code=_role(code), name="Тест", scope_all=True, permissions=perms, otp=otp))


def test_no_seed_role_mixes_admin_and_data() -> None:
    assert not any(sod_conflict(seed.permissions) for seed in ROLE_SEEDS)
    assert sod_conflict({"admin:users", WRITE})
    assert not sod_conflict({"admin:users", "audit:read"})
    assert not sod_conflict({WRITE, APPROVE})


def test_create_role_rejects_admin_plus_data(make_user: MakeUser) -> None:
    admin = ctx_of(make_user("admin", totp=False))
    with pytest.raises(ValidationFailed) as exc:
        _new_role(admin, "mix", ["admin:users", "admin:roles", WRITE])
    assert exc.value.code == "role_sod_conflict"
    _new_role(admin, "plain_data", [WRITE])  # faqat data -- ruxsat
    _new_role(admin, "plain_admin", ["admin:users"])  # faqat admin -- ruxsat


def test_update_role_rejects_mixing_both_ways(make_user: MakeUser) -> None:
    admin = ctx_of(make_user("admin", totp=False))
    data_role = _new_role(admin, "dr", [WRITE])
    admin_role = _new_role(admin, "ar", ["admin:users"])
    with pytest.raises(ValidationFailed) as exc:
        _call(admin, service.update_role, data_role.id,
              RoleUpdate(permissions=[WRITE, "admin:users"]))
    assert exc.value.code == "role_sod_conflict"
    with pytest.raises(ValidationFailed):
        _call(admin, service.update_role, admin_role.id,
              RoleUpdate(permissions=["admin:users", APPROVE]))


def test_sync_reference_does_not_mix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admin-ruxsatli rolga yangi data:* sync orqali berilmaydi."""
    from app.auth import permissions as perms_mod
    from app.auth import seed as seed_mod

    with new_session() as s:
        role_id = s.execute(select(Role.id).where(Role.code == "admin")).scalar_one()
        s.execute(text("DELETE FROM core.permissions WHERE code = :c"), {"c": WRITE})
        s.commit()
    forged = tuple(
        perms_mod.RoleSeed(r.code, r.name, r.scope_all, r.permissions | {WRITE})
        if r.code == "admin" else r
        for r in ROLE_SEEDS
    )
    monkeypatch.setattr(seed_mod, "ROLE_SEEDS", forged)
    with new_session() as s:
        sync_reference(s)
        s.commit()
        granted = s.execute(text(
            "SELECT count(*) FROM core.role_permissions WHERE role_id = :r "
            "AND permission_code = :p"), {"r": role_id, "p": WRITE}).scalar_one()
    assert granted == 0


def test_role_audit_records_effective_data_perms(make_user: MakeUser) -> None:
    admin = ctx_of(make_user("admin", totp=False))
    role = _new_role(admin, "audited", [WRITE, "audit:read"])
    created = [r for r in audit_rows("admin.role.created")
               if r["object_id"] == str(role.id)][-1]
    assert created["details"]["data_perms"] == {"added": [WRITE], "removed": []}
    _call(admin, service.update_role, role.id, RoleUpdate(permissions=["audit:read", APPROVE]))
    updated = [r for r in audit_rows("admin.role.updated")
               if r["object_id"] == str(role.id)][-1]
    assert updated["details"]["data_perms"] == {"added": [APPROVE], "removed": [WRITE]}
    events = [r for r in audit_rows("security.data_approve_granted")
              if r["object_id"] == str(role.id)]
    assert events and events[-1]["details"]["perms"] == [APPROVE]


def test_approve_grant_needs_step_up_when_actor_has_2fa(make_user: MakeUser) -> None:
    seed = make_user("admin")  # TOTP yoqilgan
    admin = ctx_of(seed)
    assert admin.mfa_enabled
    with pytest.raises(ValidationFailed) as exc:
        _new_role(admin, "needs_otp", [APPROVE])
    assert exc.value.code == "step_up_required"
    ok = _new_role(admin, "with_otp", [APPROVE], otp=seed.next_code())
    assert ok.permissions == [APPROVE]
    # write bergan rol -- step-up talab qilinmaydi
    _new_role(admin, "write_only", [WRITE])


def test_position_and_user_changes_record_data_perms(make_user: MakeUser) -> None:
    admin = ctx_of(make_user("admin", totp=False))
    checker_role = _new_role(admin, "chk", [APPROVE])
    plain_role = _new_role(admin, "pln", ["audit:read"])
    pos = _call(admin, service.create_position,
                PositionIn(code=_role("pos"), name="Тест", role_id=plain_role.id, branch_ids=[]))
    _call(admin, service.update_position, pos.id, PositionUpdate(role_id=checker_role.id))
    upd = [r for r in audit_rows("admin.position.updated") if r["object_id"] == str(pos.id)][-1]
    assert upd["details"]["data_perms"] == {"added": [APPROVE], "removed": []}
    assert [r for r in audit_rows("security.data_approve_granted")
            if r["object_id"] == str(pos.id)]
    created, _ = _call(admin, service.create_user,
                       UserCreate(username=f"sod_{pos.id}_x", full_name="Тест", position_id=pos.id))
    ev = [r for r in audit_rows("admin.user.created") if r["object_id"] == str(created.id)][-1]
    assert ev["details"]["data_perms"]["added"] == [APPROVE]
