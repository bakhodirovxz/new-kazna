import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.auth.models import Permission, Position, Role, RolePermission
from app.auth.permissions import (
    ADMIN_GUARANTEED,
    DATA_SECTIONS,
    PERMISSIONS,
    Perm,
    Section,
    data_perm,
    section_perm,
)
from app.auth.seed import sync_reference
from app.core.db import new_session

S = {s: section_perm(s) for s in Section}
W = {s: data_perm(s, "write") for s in DATA_SECTIONS}
A = {s: data_perm(s, "approve") for s in DATA_SECTIONS}
EXPORT = {Perm.EXPORT_CSV.value, Perm.EXPORT_XLSX.value}

# Spec 3.3 / TZ 1-bo'lim jadvali.
EXPECTED = {
    "rukovodstvo": (True, set(S.values()) | EXPORT),
    "nach_otdela": (True, set(S.values()) | EXPORT | set(A.values())),
    "spec_kazna": (
        True,
        {S[Section.OBZOR], S[Section.KAZNA], S[Section.KREDITY], S[Section.FINMODEL]} | EXPORT
        | {W[Section.KAZNA], W[Section.KREDITY]},
    ),
    "economist_filiala": (
        False,
        {S[Section.OBZOR], S[Section.KAZNA], S[Section.PROIZVODSTVO], S[Section.SKLAD],
         S[Section.KADRY]} | EXPORT
        | {W[Section.KAZNA], W[Section.PROIZVODSTVO], W[Section.KADRY]},
    ),
    "profil_sluzhba": (True, {S[Section.OBZOR]} | EXPORT),
    "admin": (True, set(S.values()) | {p.value for p in Perm}),
    "vnutr_kontrol": (True, {S[Section.OBZOR], Perm.AUDIT_READ.value}),
}


def _role_matrix(db: Session) -> dict[str, tuple[bool, set[str]]]:
    out: dict[str, tuple[bool, set[str]]] = {}
    for role in db.execute(select(Role).where(Role.is_system.is_(True))).scalars():
        perms = set(
            db.execute(
                select(RolePermission.permission_code).where(RolePermission.role_id == role.id)
            ).scalars()
        )
        out[role.code] = (role.scope_all, perms)
    return out


def test_permissions_table_matches_code(db: Session) -> None:
    rows = dict(db.execute(select(Permission.code, Permission.description)).tuples().all())
    assert rows == PERMISSIONS


def test_system_roles_match_spec(db: Session) -> None:
    assert _role_matrix(db) == EXPECTED


def test_each_system_role_has_a_position(db: Session) -> None:
    codes = set(db.execute(select(Position.code)).scalars())
    assert set(EXPECTED) <= codes


def test_sync_is_idempotent_and_restores_admin_guarantees() -> None:
    with new_session() as s:
        admin_id = s.execute(select(Role.id).where(Role.code == "admin")).scalar_one()
        s.execute(
            text("DELETE FROM core.role_permissions WHERE role_id = :r AND permission_code = :p"),
            {"r": admin_id, "p": Perm.ADMIN_USERS.value},
        )
        sync_reference(s)
        sync_reference(s)
        perms = set(
            s.execute(
                select(RolePermission.permission_code).where(RolePermission.role_id == admin_id)
            ).scalars()
        )
        s.commit()
    assert perms >= ADMIN_GUARANTEED


def test_username_format_is_enforced_by_db(db: Session) -> None:
    pos_id = db.execute(select(Position.id).where(Position.code == "admin")).scalar_one()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO core.users (username, full_name, position_id, password_hash) "
                "VALUES ('Bad Name', 'x', :p, 'h')"
            ),
            {"p": pos_id},
        )


def test_app_role_cannot_delete_users(db: Session) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        db.execute(text("DELETE FROM core.users"))


def test_fresh_perm_granted_once_to_system_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    perm = data_perm(Section.KAZNA, "write")

    def has() -> bool:
        with new_session() as s:
            return s.execute(text(
                "SELECT count(*) FROM core.role_permissions rp "
                "JOIN core.roles r ON r.id = rp.role_id "
                "WHERE r.code = 'spec_kazna' AND rp.permission_code = :p"), {"p": perm}
            ).scalar_one() == 1

    def drop() -> None:
        with new_session() as s:
            s.execute(text("DELETE FROM core.role_permissions rp USING core.roles r "
                           "WHERE r.id = rp.role_id AND r.code = 'spec_kazna' "
                           "AND rp.permission_code = :p"), {"p": perm})
            s.commit()

    # yangi qo'shilgan ruxsat: kodda yo'q -> bazadan ketadi -> kodga qaytadi -> bir marta beriladi
    drop()
    reduced = {k: v for k, v in PERMISSIONS.items() if k != perm}
    monkeypatch.setattr("app.auth.seed.PERMISSIONS", reduced)
    with new_session() as s:
        sync_reference(s)
        s.commit()
    monkeypatch.undo()
    with new_session() as s:
        sync_reference(s)
        s.commit()
    assert has()
    # keyin administrator olib tashlasa -- qayta qo'shilmaydi
    drop()
    with new_session() as s:
        sync_reference(s)
        s.commit()
    assert not has()
    with new_session() as s:  # keyingi testlar uchun qaytarish
        s.execute(text("INSERT INTO core.role_permissions (role_id, permission_code) "
                       "SELECT id, :p FROM core.roles WHERE code = 'spec_kazna'"), {"p": perm})
        s.commit()
