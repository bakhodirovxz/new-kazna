"""Versiyali sozlamalar (spec 4.8): har o'zgarish — yangi version qatori + audit.
Eski versiyalar o'chirilmaydi (is_current = false) — tarix va audit uchun."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.dwh_schemas import (
    AlertRuleOut,
    AlertRuleUpdate,
    FinAssumptionOut,
    FinAssumptionsUpdate,
    SettingOut,
    SettingVersionOut,
)
from app.audit.service import AuditAction, log_event
from app.auth.context import AuthContext
from app.auth.stepup import require_step_up
from app.core import sysconfig
from app.core.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailed,
)
from app.core.request_meta import ClientMeta
from app.core.sysconfig import REGISTRY, SettingDef, resolve

_RULE_COLS = ("code, version, title, section, page, threshold, level, enabled, updated_by, "
              "updated_at")


def _missing_current(db: Session, sql_exists: str, params: dict[str, Any]) -> AppError:
    """FOR UPDATE kutgandan keyin joriy qator yo'q: kod/kalit mavjud bo'lsa — poyga (409),
    aks holda 404."""
    if db.execute(text(sql_exists), params).first() is not None:
        return ConflictError("conflict_modified")
    return NotFoundError()


def _rule(row: Any) -> AlertRuleOut:
    return AlertRuleOut(**dict(row._mapping))


def list_alert_rules(db: Session) -> list[AlertRuleOut]:
    # nosemgrep: avoid-sqlalchemy-text
    rows = db.execute(text(f"SELECT {_RULE_COLS} FROM core.alert_rules WHERE is_current "
                           "ORDER BY section, code")).all()
    return [_rule(r) for r in rows]


def alert_rule_history(db: Session, code: str) -> list[AlertRuleOut]:
    # nosemgrep: avoid-sqlalchemy-text
    rows = db.execute(text(f"SELECT {_RULE_COLS} FROM core.alert_rules WHERE code = :c "
                           "ORDER BY version DESC"), {"c": code}).all()
    if not rows:
        raise NotFoundError()
    return [_rule(r) for r in rows]


def update_alert_rule(db: Session, actor: AuthContext, code: str, data: AlertRuleUpdate,
                      meta: ClientMeta) -> AlertRuleOut:
    # nosemgrep: avoid-sqlalchemy-text
    row = db.execute(text(f"SELECT {_RULE_COLS} FROM core.alert_rules "
                          "WHERE code = :c AND is_current FOR UPDATE"), {"c": code}).first()
    if row is None:
        raise _missing_current(db, "SELECT 1 FROM core.alert_rules WHERE code = :c LIMIT 1",
                               {"c": code})
    current = _rule(row)
    threshold = dict(current.threshold)
    if data.value is not None:
        threshold["value"] = data.value
    if data.op is not None:
        threshold["op"] = data.op
    level = data.level or current.level
    enabled = current.enabled if data.enabled is None else data.enabled
    if (threshold, level, enabled) == (current.threshold, current.level, current.enabled):
        return current
    version = current.version + 1
    db.execute(text("UPDATE core.alert_rules SET is_current = false "
                    "WHERE code = :c AND is_current"), {"c": code})
    db.execute(text(
        "INSERT INTO core.alert_rules (code, version, title, section, page, threshold, level, "
        "enabled, updated_by) VALUES (:c, :v, :t, :s, :p, CAST(:th AS jsonb), :l, :e, :u)"),
        {"c": code, "v": version, "t": current.title, "s": current.section, "p": current.page,
         "th": json.dumps(threshold), "l": level, "e": enabled, "u": actor.user_id})
    db.commit()  # commit-then-audit (keys_router.rotate_key)
    log_event(meta, AuditAction.ALERT_RULE_UPDATED, user_id=actor.user_id,
              object_type="alert_rule", object_id=code,
              details={"version": version,
                       "before": {"threshold": current.threshold, "level": current.level,
                                  "enabled": current.enabled},
                       "after": {"threshold": threshold, "level": level, "enabled": enabled}})
    return alert_rule_history(db, code)[0]


_FIN_COLS = "scenario, year, key, value, version, updated_by, updated_at"


def list_fin_assumptions(db: Session, scenario: str | None) -> list[FinAssumptionOut]:
    # nosemgrep: avoid-sqlalchemy-text
    rows = db.execute(text(
        f"SELECT {_FIN_COLS} FROM core.fin_assumptions WHERE is_current "
        "AND (CAST(:s AS text) IS NULL OR scenario = :s) ORDER BY scenario, year, key"),
        {"s": scenario}).all()
    return [FinAssumptionOut(**{**dict(r._mapping), "value": float(r.value)}) for r in rows]


def update_fin_assumptions(db: Session, actor: AuthContext, data: FinAssumptionsUpdate,
                           meta: ClientMeta) -> list[FinAssumptionOut]:
    changes: list[dict[str, Any]] = []
    # Deterministik tartib: parallel PUT'lar qulfni bir xil tartibda oladi (deadlock yo'q).
    for item in sorted(data.items, key=lambda i: (i.scenario, i.year, i.key)):
        key = {"s": item.scenario, "y": item.year, "k": item.key}
        row = db.execute(text(
            "SELECT version, value FROM core.fin_assumptions WHERE scenario = :s AND year = :y "
            "AND key = :k AND is_current FOR UPDATE"), key).first()
        if row is None:
            raise _missing_current(
                db, "SELECT 1 FROM core.fin_assumptions WHERE scenario = :s AND year = :y "
                "AND key = :k LIMIT 1", key)
        new_value = Decimal(str(item.value))
        if new_value == row.value:
            continue
        db.execute(text("UPDATE core.fin_assumptions SET is_current = false WHERE scenario = :s "
                        "AND year = :y AND key = :k AND is_current"), key)
        db.execute(text(
            "INSERT INTO core.fin_assumptions (scenario, year, key, version, value, updated_by) "
            "VALUES (:s, :y, :k, :v, :val, :u)"),
            {**key, "v": row.version + 1, "val": new_value, "u": actor.user_id})
        changes.append({"scenario": item.scenario, "year": item.year, "key": item.key,
                        "before": str(row.value), "after": str(new_value),
                        "version": row.version + 1})
    if changes:
        db.commit()  # commit-then-audit
        log_event(meta, AuditAction.FIN_ASSUMPTIONS_UPDATED, user_id=actor.user_id,
                  object_type="fin_assumptions", object_id="batch",
                  details={"changes": changes})
    return list_fin_assumptions(db, None)


def _setting_row(db: Session, key: str, lock: bool = False) -> Any:
    suffix = " FOR UPDATE" if lock else ""
    # nosemgrep: avoid-sqlalchemy-text
    return db.execute(text("SELECT key, value, version, updated_by, updated_at FROM core.settings "
                           f"WHERE key = :k AND is_current{suffix}"), {"k": key}).first()


_ROW_COLS = "key, value, version, updated_by, updated_at"


def require_reason(reason: str | None) -> str:
    cleaned = " ".join((reason or "").split())
    if len(cleaned) < 5:
        raise ValidationFailed("reason_required", fields=["reason"])
    return cleaned


def _out(d: SettingDef, row: Any | None) -> SettingOut:
    value, source = resolve(d, {} if row is None else {d.key: row.value})
    return SettingOut(
        key=d.key, value=value, version=0 if row is None else row.version,
        updated_by=None if row is None else row.updated_by,
        updated_at=None if row is None else row.updated_at,
        default=resolve(d, {})[0], source=source, category=d.category, title=d.title,
        kind=d.kind, perm=d.perm.value, guarded=d.guarded, step_up=d.step_up, apply=d.apply,
        unit=d.unit, lo=d.lo, hi=d.hi)


def setting_out(db: Session, key: str) -> SettingOut:
    return _out(REGISTRY[key], _setting_row(db, key))


def list_settings(db: Session, actor: AuthContext) -> list[SettingOut]:
    rows = {r.key: r for r in db.execute(text(
        f"SELECT {_ROW_COLS} FROM core.settings WHERE is_current")).all()}
    return [_out(d, rows.get(d.key)) for d in REGISTRY.values()
            if d.category != "integrations" and actor.has(d.perm)]


def _readable(actor: AuthContext, key: str) -> SettingDef:
    d = REGISTRY.get(key)
    if d is None:
        raise NotFoundError()
    if not actor.has(d.perm):
        raise ForbiddenError()
    return d


def setting_history(db: Session, actor: AuthContext, key: str) -> list[SettingVersionOut]:
    _readable(actor, key)
    rows = db.execute(text("SELECT version, value, updated_by, updated_at FROM core.settings "
                           "WHERE key = :k ORDER BY version DESC LIMIT 100"), {"k": key}).all()
    return [SettingVersionOut(**dict(r._mapping)) for r in rows]


def write_setting(db: Session, key: str, normalized: Any, user_id: int | None, *,
                  row: Any = None, locked: bool = False) -> tuple[int | None, Any]:
    """Yangi versiya (commit'siz). Qiymat o'zgarmasa (None, joriy). Parallel yozuv → 409.

    `locked=True` — chaqiruvchi qatorni allaqachon FOR UPDATE bilan o'qigan (`row`): poygada
    yutqazgan so'rov qayta o'qimaydi, (key, version) unique buzilishi → 409 (R2)."""
    if not locked:
        row = _setting_row(db, key, lock=True)
    before = None if row is None else row.value
    if row is not None and row.value == normalized:
        return None, before
    version = 1 if row is None else row.version + 1
    try:
        with db.begin_nested():
            db.execute(text("UPDATE core.settings SET is_current = false WHERE key = :k "
                            "AND is_current"), {"k": key})
            db.execute(text("INSERT INTO core.settings (key, version, value, updated_by) "
                            "VALUES (:k, :v, CAST(:val AS jsonb), :u)"),
                       {"k": key, "v": version, "val": json.dumps(normalized), "u": user_id})
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) != "23505":  # faqat unique buzilishi — poyga
            raise
        raise ConflictError("conflict_modified") from exc
    return version, before


def update_setting(db: Session, actor: AuthContext, key: str, value: Any, meta: ClientMeta, *,
                   expected_version: int | None = None, reason: str | None = None,
                   otp: str | None = None) -> SettingOut:
    d = REGISTRY.get(key)
    if d is None or d.category == "integrations":  # integratsiya maydoni — /admin/integrations
        raise NotFoundError()
    if not actor.has(d.perm):
        log_event(meta, AuditAction.ACCESS_DENIED, user_id=actor.user_id, result="denied",
                  details={"setting": key, "required": [d.perm.value]})
        raise ForbiddenError()
    try:
        normalized = d.validate(value)
    except ValueError as exc:
        raise ValidationFailed("invalid_setting", fields=["value"], key=key, lo=d.lo,
                               hi=d.hi) from exc
    cleaned = require_reason(reason) if d.guarded else None
    if d.step_up:  # qiymat tekshiruvidan keyin: xato yozuv kodni "yoqib" yubormasin
        require_step_up(db, actor, otp, meta)
    row = _setting_row(db, key, lock=True)
    if expected_version is not None and expected_version != (0 if row is None else row.version):
        raise ConflictError("conflict_modified")
    version, before = write_setting(db, key, normalized, actor.user_id, row=row, locked=True)
    db.commit()  # commit-then-audit; step-up qadami ham saqlanadi
    if version is not None:
        details: dict[str, Any] = {"version": version, "before": before, "after": normalized}
        if cleaned:
            details["reason"] = cleaned
        log_event(meta, AuditAction.SETTING_UPDATED, user_id=actor.user_id,
                  object_type="setting", object_id=key, details=details)
        sysconfig.invalidate()
    return setting_out(db, key)
