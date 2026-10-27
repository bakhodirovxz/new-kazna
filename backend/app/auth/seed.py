"""Ruxsatlar va tizim rollarini koddan bazaga sinxronlash (idempotent)."""

from __future__ import annotations

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.auth.models import Permission, Position, Role, RolePermission
from app.auth.permissions import ADMIN_GUARANTEED, ADMIN_ROLE, PERMISSIONS, ROLE_SEEDS


def sync_reference(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_sync_reference'))"))
    existing = set(db.execute(select(Permission.code)).scalars())
    for code, description in PERMISSIONS.items():
        db.execute(
            pg_insert(Permission)
            .values(code=code, description=description)
            .on_conflict_do_update(
                index_elements=[Permission.code], set_={"description": description}
            )
        )
    db.execute(delete(Permission).where(Permission.code.not_in(list(PERMISSIONS))))

    for seed in ROLE_SEEDS:
        role = db.execute(select(Role).where(Role.code == seed.code)).scalar_one_or_none()
        if role is None:
            role = Role(code=seed.code, name=seed.name, scope_all=seed.scope_all, is_system=True)
            db.add(role)
            db.flush()
            for perm in sorted(seed.permissions):
                db.add(RolePermission(role_id=role.id, permission_code=perm))
        if db.execute(select(Position.id).where(Position.code == seed.code)).first() is None:
            db.add(Position(code=seed.code, name=seed.name, role_id=role.id))

    admin_id = db.execute(select(Role.id).where(Role.code == ADMIN_ROLE)).scalar_one()
    admin_seed = next(s for s in ROLE_SEEDS if s.code == ADMIN_ROLE).permissions
    # Kodga yangi qo'shilgan admin ruxsati mavjud admin roliga BIR MARTA beriladi; keyin
    # olib tashlansa qayta qo'shilmaydi. Bo'sh bazada rol seed'i o'zi hammasini beradi.
    fresh = (set(PERMISSIONS) - existing) & admin_seed if existing else set()
    for perm in sorted(ADMIN_GUARANTEED | fresh):
        db.execute(
            pg_insert(RolePermission)
            .values(role_id=admin_id, permission_code=perm)
            .on_conflict_do_nothing()
        )
    db.flush()
