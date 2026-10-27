"""«Требует внимания» chegaralari, финмодель допущения, tizim sozlamalari (admin:settings)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.admin import config_service as service
from app.admin.dwh_schemas import (
    AlertRuleOut,
    AlertRuleUpdate,
    FinAssumptionOut,
    FinAssumptionsUpdate,
    SettingOut,
    SettingUpdate,
    SettingVersionOut,
)
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core.db import DB
from app.core.request_meta import Meta

router = APIRouter(prefix="/admin", tags=["admin"])
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


SettingsReader = Annotated[AuthContext, Depends(require_perm(
    Perm.ADMIN_SETTINGS, Perm.ADMIN_SECURITY, Perm.ADMIN_INTEGRATIONS, any_of=True))]


@router.get("/settings")
def list_settings(ctx: SettingsReader, db: DB) -> list[SettingOut]:
    return service.list_settings(db, ctx)


@router.get("/settings/{key}/history")
def setting_history(key: str, ctx: SettingsReader, db: DB) -> list[SettingVersionOut]:
    return service.setting_history(db, ctx, key)


@router.put("/settings/{key}")
def update_setting(key: str, body: SettingUpdate, ctx: SettingsReader, db: DB,
                   meta: Meta) -> SettingOut:
    # Kalit ruxsati (d.perm) servisda tekshiriladi va rad etish auditga yoziladi.
    return service.update_setting(db, ctx, key, body.value, meta,
                                  expected_version=body.expected_version, reason=body.reason,
                                  otp=body.otp)
