"""Integratsiyalar va ularning hisob ma'lumotlari (admin:integrations)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.admin import integrations_service as service
from app.admin.dwh_schemas import IntegrationCheckOut, IntegrationOut, IntegrationUpdate
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core.db import DB
from app.core.request_meta import Meta

router = APIRouter(prefix="/admin/integrations", tags=["admin"])
IntegrationsAdmin = Annotated[AuthContext, Depends(require_perm(Perm.ADMIN_INTEGRATIONS))]
Name = Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]{1,31}$")]


@router.get("")
def list_integrations(ctx: IntegrationsAdmin, db: DB) -> list[IntegrationOut]:
    return service.list_integrations(db)


@router.put("/{name}")
def update_integration(name: Name, body: IntegrationUpdate, ctx: IntegrationsAdmin, db: DB,
                       meta: Meta) -> IntegrationOut:
    return service.update_integration(db, ctx, name, body, meta)


@router.post("/{name}/check", status_code=202)
def request_check(name: Name, ctx: IntegrationsAdmin, db: DB,
                  meta: Meta) -> IntegrationCheckOut:
    return service.request_check(db, ctx, name, meta)


@router.get("/checks/{check_id}")
def get_check(check_id: Annotated[int, Path(gt=0)], ctx: IntegrationsAdmin,
              db: DB) -> IntegrationCheckOut:
    return service.get_check(db, check_id)
