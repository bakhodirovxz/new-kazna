"""Admin amallari. Har o'zgarish auditga yoziladi; kamida bitta faol administrator qoladi."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import Select, delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.schemas import (
    PermissionOut,
    PositionIn,
    PositionOut,
    PositionRef,
    PositionUpdate,
    RoleIn,
    RoleOut,
    RoleUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.audit.service import AuditAction, log_event
from app.auth import passwords, sessions
from app.auth.context import AuthContext
from app.auth.models import (
    BackupCode,
    MfaChallenge,
    Permission,
    Position,
    PositionBranch,
    Role,
    RolePermission,
    User,
)
from app.auth.permissions import ADMIN_GUARANTEED, ADMIN_ROLE
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from app.core.request_meta import ClientMeta


def _now() -> datetime:
    return datetime.now(UTC)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _invalidate_mfa_challenges(db: Session, user_id: int, now: datetime) -> None:
    """Foydalanuvchining barcha ochiq MFA challenge'larini bekor qiladi.

    Admin foydalanuvchini bloklaganda, parolini yoki 2FA'sini qayta o'rnatganda yoki
    lavozimini o'zgartirganda chaqiriladi — chaqiruvchi buni FOYDALANUVCHI qatorini
    `with_for_update=True` bilan qulflab olgandan KEYIN qiladi (qulf tartibi
    `app.auth.service`dagi bilan bir xil: avval user, keyin challenge)."""
    db.execute(
        update(MfaChallenge)
        .where(MfaChallenge.user_id == user_id, MfaChallenge.used_at.is_(None))
        .values(used_at=now, pending_secret_enc=None)
    )


def assert_admin_remains(db: Session) -> None:
    """I1/I2 (fix r1): `pg_advisory_xact_lock` ikkita parallel tranzaksiya (masalan, ikkita
    administrator bir-birini bir vaqtda bloklasa) sonlashni ketma-ketlashtiradi — aks holda
    READ COMMITTED ostida ikkalasi ham "hali kamida bitta admin bor" deb hisoblab, ikkalasi
    ham committing bo'lib, nol administrator qolishi mumkin edi. Invariant — kamida bitta
    FAOL foydalanuvchi FAOL lavozimda ega rol ADMIN_GUARANTEED'ning BARCHASINI (admin:users
    VA admin:roles) ushlab turishi kerak — faqat admin:users yetarli emas (I2)."""
    db.flush()
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_last_admin'))"))
    guaranteed = sorted(ADMIN_GUARANTEED)
    admin_roles = (
        select(RolePermission.role_id)
        .where(RolePermission.permission_code.in_(guaranteed))
        .group_by(RolePermission.role_id)
        .having(func.count(func.distinct(RolePermission.permission_code)) == len(guaranteed))
    )
    count = db.execute(
        select(func.count(User.id))
        .join(Position, Position.id == User.position_id)
        .where(
            User.is_active.is_(True),
            Position.is_active.is_(True),
            Position.role_id.in_(admin_roles),
        )
    ).scalar_one()
    if count == 0:
        raise ConflictError("last_admin")


def _role_permission_codes(db: Session, role_id: int) -> frozenset[str]:
    return frozenset(
        db.execute(
            select(RolePermission.permission_code).where(RolePermission.role_id == role_id)
        ).scalars()
    )


def _assert_no_escalation(actor: AuthContext, granted: Iterable[str]) -> None:
    """I3: admin endpointlari orqali actor o'zida yo'q ruxsatni hech kimga bera olmaydi."""
    if not set(granted) <= actor.permissions:
        raise ForbiddenError("privilege_escalation")


def _user_query() -> Select[tuple[User, Position, str]]:
    return (
        select(User, Position, Role.code)
        .join(Position, Position.id == User.position_id)
        .join(Role, Role.id == Position.role_id)
    )


def _to_out(user: User, position: Position, role_code: str) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        position=PositionRef(id=position.id, code=position.code, name=position.name),
        role_code=role_code,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        locked_until=user.locked_until,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


def get_user_out(db: Session, user_id: int) -> UserOut:
    db.flush()
    row = db.execute(_user_query().where(User.id == user_id)).first()
    if row is None:
        raise NotFoundError()
    user, position, role_code = row
    db.refresh(user)
    return _to_out(user, position, role_code)


def list_users(db: Session, q: str | None, page: int, page_size: int) -> tuple[list[UserOut], int]:
    query = _user_query()
    if q:
        like = f"%{_escape_like(q.strip().lower())}%"
        query = query.where(
            or_(
                User.username.like(like, escape="\\"),
                func.lower(User.full_name).like(like, escape="\\"),
            )
        )
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(User.username).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return [_to_out(*row) for row in rows], int(total)


def _load_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id, with_for_update=True)
    if user is None:
        raise NotFoundError()
    return user


def _require_position(db: Session, position_id: int) -> Position:
    position = db.get(Position, position_id)
    if position is None or not position.is_active:
        raise ValidationFailed("validation_failed", fields=["position_id"])
    return position


def _not_self(actor: AuthContext, user_id: int) -> None:
    if actor.user_id == user_id:
        raise ConflictError("cannot_modify_self")


def create_user(
    db: Session, actor: AuthContext, data: UserCreate, meta: ClientMeta
) -> tuple[UserOut, str]:
    position = _require_position(db, data.position_id)
    # I3: yangi foydalanuvchining lavozimi orqali beriladigan rol ruxsatlari actor'da
    # yo'q ruxsatlarni o'z ichiga olmasin (imtiyoz eskalatsiyasi).
    _assert_no_escalation(actor, _role_permission_codes(db, position.role_id))
    if db.execute(select(User.id).where(User.username == data.username)).first() is not None:
        raise ConflictError("username_taken")
    temporary = passwords.generate_temporary_password()
    user = User(
        username=data.username,
        full_name=data.full_name,
        position_id=data.position_id,
        password_hash=passwords.hash_password(temporary),
        password_changed_at=_now(),
        must_change_password=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        # Ledger: har qanday IntegrityError username_taken'ga tushiriladi — boshqa FK/CHECK
        # buzilishi hozircha yo'q (branch_ids FK Plan 2'da keladi).
        raise ConflictError("username_taken") from exc
    log_event(
        meta,
        AuditAction.USER_CREATED,
        user_id=actor.user_id,
        object_type="user",
        object_id=user.id,
        details={"username": user.username, "position_id": user.position_id},
    )
    return get_user_out(db, user.id), temporary


def update_user(
    db: Session, actor: AuthContext, user_id: int, data: UserUpdate, meta: ClientMeta
) -> UserOut:
    user = _load_user(db, user_id)
    changes: dict[str, object] = {}
    if data.full_name is not None and data.full_name != user.full_name:
        user.full_name = data.full_name
        changes["full_name"] = True
    if data.position_id is not None and data.position_id != user.position_id:
        _not_self(actor, user_id)
        position = _require_position(db, data.position_id)
        # I3: lavozim (demak, rol) o'zgartirilganda ham eskalatsiya taqiqlanadi.
        _assert_no_escalation(actor, _role_permission_codes(db, position.role_id))
        changes["position_id"] = [user.position_id, data.position_id]
        user.position_id = data.position_id
        now = _now()
        _invalidate_mfa_challenges(db, user.id, now)
        sessions.revoke_all(db, user.id, "position_changed", now)
        assert_admin_remains(db)
    if changes:
        log_event(meta, AuditAction.USER_UPDATED, user_id=actor.user_id, object_type="user",
                  object_id=user.id, details=changes)
    return get_user_out(db, user.id)


def set_active(
    db: Session, actor: AuthContext, user_id: int, active: bool, meta: ClientMeta
) -> UserOut:
    _not_self(actor, user_id)
    user = _load_user(db, user_id)
    user.is_active = active
    if active:
        user.failed_logins = 0
        user.locked_until = None
    else:
        now = _now()
        _invalidate_mfa_challenges(db, user.id, now)
        sessions.revoke_all(db, user.id, "blocked", now)
        assert_admin_remains(db)
    log_event(meta, AuditAction.USER_UNBLOCKED if active else AuditAction.USER_BLOCKED,
              user_id=actor.user_id, object_type="user", object_id=user.id)
    return get_user_out(db, user.id)


def reset_password(db: Session, actor: AuthContext, user_id: int, meta: ClientMeta) -> str:
    _not_self(actor, user_id)
    user = _load_user(db, user_id)
    now = _now()
    temporary = passwords.generate_temporary_password()
    user.password_hash = passwords.hash_password(temporary)
    user.password_changed_at = now
    user.must_change_password = True
    user.failed_logins = 0
    user.locked_until = None
    _invalidate_mfa_challenges(db, user.id, now)
    sessions.revoke_all(db, user.id, "password_reset", now)
    log_event(meta, AuditAction.USER_PASSWORD_RESET, user_id=actor.user_id, object_type="user",
              object_id=user.id)
    return temporary


def reset_mfa(db: Session, actor: AuthContext, user_id: int, meta: ClientMeta) -> None:
    _not_self(actor, user_id)
    user = _load_user(db, user_id)
    now = _now()
    user.totp_enabled = False
    user.totp_secret_enc = None
    user.totp_last_step = None
    db.execute(delete(BackupCode).where(BackupCode.user_id == user.id))
    _invalidate_mfa_challenges(db, user.id, now)
    sessions.revoke_all(db, user.id, "mfa_reset", now)
    log_event(meta, AuditAction.USER_MFA_RESET, user_id=actor.user_id, object_type="user",
              object_id=user.id)


# ── Ruxsatlar va rollar ─────────────────────────────────────────────
def list_permissions(db: Session) -> list[PermissionOut]:
    rows = db.execute(select(Permission).order_by(Permission.code)).scalars()
    return [PermissionOut(code=p.code, description=p.description) for p in rows]


def _role_out(db: Session, role: Role) -> RoleOut:
    perms = sorted(_role_permission_codes(db, role.id))
    return RoleOut(id=role.id, code=role.code, name=role.name, scope_all=role.scope_all,
                   is_system=role.is_system, permissions=perms)


def list_roles(db: Session) -> list[RoleOut]:
    return [_role_out(db, r) for r in db.execute(select(Role).order_by(Role.code)).scalars()]


def _validate_permissions(db: Session, codes: list[str]) -> list[str]:
    unique = sorted(set(codes))
    known = set(db.execute(select(Permission.code).where(Permission.code.in_(unique))).scalars())
    unknown = [c for c in unique if c not in known]
    if unknown:
        raise ValidationFailed("unknown_permission", permissions=unknown)
    return unique


def _set_permissions(db: Session, role_id: int, codes: list[str]) -> None:
    db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    for code in codes:
        db.add(RolePermission(role_id=role_id, permission_code=code))


def create_role(db: Session, actor: AuthContext, data: RoleIn, meta: ClientMeta) -> RoleOut:
    perms = _validate_permissions(db, data.permissions)
    # I3: actor faqat o'zida bor ruxsatlarni yangi rolga bera oladi.
    _assert_no_escalation(actor, perms)
    if db.execute(select(Role.id).where(Role.code == data.code)).first() is not None:
        raise ConflictError("code_taken")
    role = Role(code=data.code, name=data.name, scope_all=data.scope_all, is_system=False)
    db.add(role)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("code_taken") from exc
    _set_permissions(db, role.id, perms)
    db.flush()
    log_event(meta, AuditAction.ROLE_CREATED, user_id=actor.user_id, object_type="role",
              object_id=role.id, details={"code": role.code, "permissions": perms})
    return _role_out(db, role)


def update_role(
    db: Session, actor: AuthContext, role_id: int, data: RoleUpdate, meta: ClientMeta
) -> RoleOut:
    role = db.get(Role, role_id, with_for_update=True)
    if role is None:
        raise NotFoundError()
    # I3: actor o'z rolini (o'z lavozimidagi rolni) tahrirlay olmaydi — aks holda o'zini
    # tasodifan huquqlardan mahrum qilishi yoki (rol bo'lsa) kengaytirishi mumkin edi.
    if role.code == actor.role_code:
        raise ConflictError("cannot_modify_self")
    details: dict[str, object] = {}
    if data.name is not None:
        role.name = data.name
        details["name"] = data.name
    if data.scope_all is not None:
        role.scope_all = data.scope_all
        details["scope_all"] = data.scope_all
    if data.permissions is not None:
        perms = _validate_permissions(db, data.permissions)
        _assert_no_escalation(actor, perms)
        if role.code == ADMIN_ROLE and not set(perms) >= ADMIN_GUARANTEED:
            raise ConflictError("admin_role_protected")
        _set_permissions(db, role.id, perms)
        details["permissions"] = perms
        assert_admin_remains(db)
    db.flush()
    log_event(meta, AuditAction.ROLE_UPDATED, user_id=actor.user_id, object_type="role",
              object_id=role.id, details=details)
    return _role_out(db, role)


# ── Lavozimlar ──────────────────────────────────────────────────────
def _position_out(db: Session, position: Position) -> PositionOut:
    role_code = db.execute(select(Role.code).where(Role.id == position.role_id)).scalar_one()
    branches = sorted(
        db.execute(
            select(PositionBranch.branch_id).where(PositionBranch.position_id == position.id)
        ).scalars()
    )
    return PositionOut(
        id=position.id,
        code=position.code,
        name=position.name,
        role_id=position.role_id,
        role_code=role_code,
        is_active=position.is_active,
        branch_ids=branches,
    )


def list_positions(db: Session) -> list[PositionOut]:
    rows = db.execute(select(Position).order_by(Position.code)).scalars()
    return [_position_out(db, p) for p in rows]


def _set_branches(db: Session, position_id: int, branch_ids: list[int]) -> None:
    db.execute(delete(PositionBranch).where(PositionBranch.position_id == position_id))
    for branch in sorted(set(branch_ids)):
        db.add(PositionBranch(position_id=position_id, branch_id=branch))


def _require_role(db: Session, role_id: int) -> None:
    if db.get(Role, role_id) is None:
        raise ValidationFailed("validation_failed", fields=["role_id"])


def create_position(
    db: Session, actor: AuthContext, data: PositionIn, meta: ClientMeta
) -> PositionOut:
    _require_role(db, data.role_id)
    if db.execute(select(Position.id).where(Position.code == data.code)).first() is not None:
        raise ConflictError("code_taken")
    position = Position(code=data.code, name=data.name, role_id=data.role_id)
    db.add(position)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("code_taken") from exc
    _set_branches(db, position.id, data.branch_ids)
    db.flush()
    log_event(meta, AuditAction.POSITION_CREATED, user_id=actor.user_id, object_type="position",
              object_id=position.id, details={"code": position.code, "role_id": position.role_id,
                                              "branch_ids": sorted(set(data.branch_ids))})
    return _position_out(db, position)


def update_position(
    db: Session, actor: AuthContext, position_id: int, data: PositionUpdate, meta: ClientMeta
) -> PositionOut:
    # I3: actor o'z lavozimini tahrirlay olmaydi (masalan, o'z filial doirasini kengaytirib
    # qo'yishi mumkin edi).
    actor_position_id = db.execute(
        select(User.position_id).where(User.id == actor.user_id)
    ).scalar_one()
    if actor_position_id == position_id:
        raise ConflictError("cannot_modify_self")
    position = db.get(Position, position_id, with_for_update=True)
    if position is None:
        raise NotFoundError()
    details: dict[str, object] = {}
    scope_changed = False
    if data.name is not None:
        position.name = data.name
        details["name"] = data.name
    if data.role_id is not None and data.role_id != position.role_id:
        _require_role(db, data.role_id)
        # I3: lavozimning roli o'zgartirilganda ham eskalatsiya taqiqlanadi.
        _assert_no_escalation(actor, _role_permission_codes(db, data.role_id))
        details["role_id"] = [position.role_id, data.role_id]
        position.role_id = data.role_id
        scope_changed = True
    if data.branch_ids is not None:
        _set_branches(db, position.id, data.branch_ids)
        details["branch_ids"] = sorted(set(data.branch_ids))
        scope_changed = True
    if data.is_active is not None and data.is_active != position.is_active:
        position.is_active = data.is_active
        details["is_active"] = data.is_active
        scope_changed = True
    if scope_changed:
        now = _now()
        # I4: shu lavozimdagi barcha foydalanuvchilar avval ID tartibida qulflanadi (deadlock
        # oldini olish uchun izchil tartib), so'ng har biriga ham ochiq MFA challenge'lari,
        # ham sessiyalari bekor qilinadi.
        user_ids = (
            db.execute(
                select(User.id)
                .where(User.position_id == position.id)
                .order_by(User.id)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        for user_id in user_ids:
            _invalidate_mfa_challenges(db, user_id, now)
            sessions.revoke_all(db, user_id, "position_changed", now)
        assert_admin_remains(db)
    db.flush()
    log_event(meta, AuditAction.POSITION_UPDATED, user_id=actor.user_id, object_type="position",
              object_id=position.id, details=details)
    return _position_out(db, position)
