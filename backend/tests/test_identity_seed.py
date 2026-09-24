import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.auth.models import Permission, Position, Role, RolePermission
from app.auth.permissions import ADMIN_GUARANTEED, PERMISSIONS, Perm, Section, section_perm
from app.auth.seed import sync_reference
from app.core.db import new_session

S = {s: section_perm(s) for s in Section}
EXPORT = {Perm.EXPORT_CSV.value, Perm.EXPORT_XLSX.value}

# Spec 3.3 / TZ 1-bo'lim jadvali.
EXPECTED = {
    "rukovodstvo": (True, set(S.values()) | EXPORT),
    "nach_otdela": (True, set(S.values()) | EXPORT),
    "spec_kazna": (
        True,
        {S[Section.OBZOR], S[Section.KAZNA], S[Section.KREDITY], S[Section.FINMODEL]} | EXPORT,
    ),
    "economist_filiala": (
        False,
        {S[Section.OBZOR], S[Section.KAZNA], S[Section.PROIZVODSTVO], S[Section.SKLAD],
         S[Section.KADRY]} | EXPORT,
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
