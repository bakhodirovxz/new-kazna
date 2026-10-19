"""«Требует внимания» chegaralari, финмодель допущения, tizim sozlamalari (admin:settings)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin import config_service as service
from app.admin.dwh_schemas import (
    AlertRuleOut,
    AlertRuleUpdate,
    FinAssumptionOut,
    FinAssumptionsUpdate,
    SettingOut,
    SettingUpdate,
)
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core.db import get_db
from app.core.request_meta import Meta

router = APIRouter(prefix="/admin", tags=["admin"])
DB = Annotated[Session, Depends(get_db)]
SettingsAdmin = Annotated[AuthContext, Depends(require_perm(Perm.ADMIN_SETTINGS))]


@router.get("/alert-rules")
def list_alert_rules(ctx: SettingsAdmin, db: DB) -> list[AlertRuleOut]:
    return service.list_alert_rules(db)


@router.get("/alert-rules/{code}/history")
def alert_rule_history(code: str, ctx: SettingsAdmin, db: DB) -> list[AlertRuleOut]:
    return service.alert_rule_history(db, code)


@router.patch("/alert-rules/{code}")
def update_alert_rule(code: str, body: AlertRuleUpdate, ctx: SettingsAdmin, db: DB,
                      meta: Meta) -> AlertRuleOut:
    return service.update_alert_rule(db, ctx, code, body, meta)


@router.get("/fin-assumptions")
def list_fin_assumptions(
    ctx: SettingsAdmin,
    db: DB,
    scenario: Annotated[str | None, Query(pattern=r"^(base|water|tariff|fx)$")] = None,
) -> list[FinAssumptionOut]:
    return service.list_fin_assumptions(db, scenario)


@router.put("/fin-assumptions")
def update_fin_assumptions(body: FinAssumptionsUpdate, ctx: SettingsAdmin, db: DB,
                           meta: Meta) -> list[FinAssumptionOut]:
    return service.update_fin_assumptions(db, ctx, body, meta)


@router.get("/settings")
def list_settings(ctx: SettingsAdmin, db: DB) -> list[SettingOut]:
    return service.list_settings(db)


@router.put("/settings/{key}")
def update_setting(key: str, body: SettingUpdate, ctx: SettingsAdmin, db: DB,
                   meta: Meta) -> SettingOut:
    return service.update_setting(db, ctx, key, body.value, meta)
