"""Admin endpointlari: foydalanuvchilar (admin:users), rollar va lavozimlar (admin:roles)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.admin import service
from app.admin.schemas import (
    Page,
    PermissionOut,
    PositionIn,
    PositionOut,
    PositionUpdate,
    RoleIn,
    RoleOut,
    RoleUpdate,
    TemporaryPassword,
    UserCreate,
    UserCreated,
    UserOut,
    UserUpdate,
)
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core.db import DB
from app.core.request_meta import Meta

router = APIRouter(prefix="/admin", tags=["admin"])
UsersAdmin = Annotated[AuthContext, Depends(require_perm(Perm.ADMIN_USERS))]
RolesAdmin = Annotated[AuthContext, Depends(require_perm(Perm.ADMIN_ROLES))]


@router.get("/users")
def list_users(
    ctx: UsersAdmin,
    db: DB,
    q: Annotated[str | None, Query(max_length=64)] = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Page[UserOut]:
    items, total = service.list_users(db, q, page, page_size)
    return Page[UserOut](items=items, total=total, page=page, page_size=page_size)


@router.post("/users", status_code=201)
def create_user(body: UserCreate, ctx: UsersAdmin, db: DB, meta: Meta) -> UserCreated:
    user, temporary = service.create_user(db, ctx, body, meta)
    return UserCreated(user=user, temporary_password=temporary)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, ctx: UsersAdmin, db: DB, meta: Meta) -> UserOut:
    return service.update_user(db, ctx, user_id, body, meta)


@router.post("/users/{user_id}/block")
def block_user(user_id: int, ctx: UsersAdmin, db: DB, meta: Meta) -> UserOut:
    return service.set_active(db, ctx, user_id, False, meta)


@router.post("/users/{user_id}/unblock")
def unblock_user(user_id: int, ctx: UsersAdmin, db: DB, meta: Meta) -> UserOut:
    return service.set_active(db, ctx, user_id, True, meta)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, ctx: UsersAdmin, db: DB, meta: Meta) -> TemporaryPassword:
    return TemporaryPassword(temporary_password=service.reset_password(db, ctx, user_id, meta))


@router.post("/users/{user_id}/reset-2fa", status_code=204)
def reset_2fa(user_id: int, ctx: UsersAdmin, db: DB, meta: Meta) -> Response:
    service.reset_mfa(db, ctx, user_id, meta)
    return Response(status_code=204)


@router.get("/permissions")
def list_permissions(ctx: RolesAdmin, db: DB) -> list[PermissionOut]:
    return service.list_permissions(db)


@router.get("/roles")
def list_roles(ctx: RolesAdmin, db: DB) -> list[RoleOut]:
    return service.list_roles(db)


@router.post("/roles", status_code=201)
def create_role(body: RoleIn, ctx: RolesAdmin, db: DB, meta: Meta) -> RoleOut:
    return service.create_role(db, ctx, body, meta)


@router.patch("/roles/{role_id}")
def update_role(role_id: int, body: RoleUpdate, ctx: RolesAdmin, db: DB, meta: Meta) -> RoleOut:
    return service.update_role(db, ctx, role_id, body, meta)


@router.get("/positions")
def list_positions(ctx: RolesAdmin, db: DB) -> list[PositionOut]:
    return service.list_positions(db)


@router.post("/positions", status_code=201)
def create_position(body: PositionIn, ctx: RolesAdmin, db: DB, meta: Meta) -> PositionOut:
    return service.create_position(db, ctx, body, meta)


@router.patch("/positions/{position_id}")
def update_position(
    position_id: int, body: PositionUpdate, ctx: RolesAdmin, db: DB, meta: Meta
) -> PositionOut:
    return service.update_position(db, ctx, position_id, body, meta)
