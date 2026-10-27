"""Integratsiyalar: maydonlar (versiyali sozlamalar), sirlar (write-only), tekshiruv navbati."""
# ruff: noqa: S608 -- f-string faqat doimiy _CHECK_COLS ustun ro'yxati

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin.config_service import require_reason, setting_out, write_setting
from app.admin.dwh_schemas import (
    IntegrationCheckOut,
    IntegrationOut,
    IntegrationUpdate,
    SecretStatusOut,
)
from app.audit.service import AuditAction, log_event
from app.auth.context import AuthContext
from app.auth.stepup import require_step_up
from app.core import sysconfig
from app.core.errors import NotFoundError, ValidationFailed
from app.core.integrations import (
    INTEGRATIONS,
    RULES,
    IntegrationDef,
    clear_secret,
    secret_state,
    store_secret,
)
from app.core.logging import get_logger
from app.core.request_meta import ClientMeta
from app.core.sysconfig import REGISTRY

log = get_logger("ugekazna.integrations")
_CHECK_COLS = "id, name, status, code, requested_at, finished_at"


def _integration(name: str) -> IntegrationDef:
    integ = INTEGRATIONS.get(name)
    if integ is None:
        raise NotFoundError()
    return integ


def _last_check(db: Session, name: str) -> IntegrationCheckOut | None:
    row = db.execute(text(
        f"SELECT {_CHECK_COLS} FROM core.integration_checks WHERE name = :n "
        "ORDER BY id DESC LIMIT 1"), {"n": name}).first()
    return None if row is None else IntegrationCheckOut(**dict(row._mapping))


def get_integration(db: Session, name: str) -> IntegrationOut:
    integ = _integration(name)
    conn = db.connection()
    secrets = []
    for sd in integ.secrets:
        state, at, by = secret_state(conn, sd.name)
        secrets.append(SecretStatusOut(name=sd.name, title=sd.title, state=state, updated_at=at,
                                       updated_by=by))
    return IntegrationOut(name=integ.name, title=integ.title, check_in=integ.check_in,
                          endpoint=list(integ.endpoint),
                          fields=[setting_out(db, key) for key in integ.fields],
                          secrets=secrets, last_check=_last_check(db, name))


def list_integrations(db: Session) -> list[IntegrationOut]:
    return [get_integration(db, name) for name in INTEGRATIONS]


def update_integration(db: Session, actor: AuthContext, name: str, body: IntegrationUpdate,
                       meta: ClientMeta) -> IntegrationOut:
    integ = _integration(name)
    secret_defs = {sd.name: sd for sd in integ.secrets}
    unknown = sorted((set(body.values) - set(integ.fields))
                     | (set(body.secrets) - set(secret_defs)))
    if unknown:
        raise ValidationFailed("validation_failed", fields=unknown)
    normalized: dict[str, Any] = {}
    for key, raw in sorted(body.values.items()):
        try:
            normalized[key] = REGISTRY[key].validate(raw)
        except ValueError as exc:
            d = REGISTRY[key]
            raise ValidationFailed("invalid_setting", fields=[key], key=key, lo=d.lo,
                                   hi=d.hi) from exc
    for sname, plain in body.secrets.items():
        try:
            if plain is not None:
                secret_defs[sname].validate(plain)
        except ValueError as exc:
            raise ValidationFailed("invalid_secret", fields=[sname]) from exc
    reason = require_reason(body.reason)
    if not normalized and not body.secrets:
        return get_integration(db, name)
    require_step_up(db, actor, body.otp, meta)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_integration_' || :n))"),
               {"n": name})
    changes: list[dict[str, Any]] = []
    for key, new in normalized.items():
        version, before = write_setting(db, key, new, actor.user_id)
        if version is not None:
            changes.append({"key": key, "before": before, "after": new, "version": version})
    endpoint_changed = any(c["key"] in integ.endpoint for c in changes)
    conn = db.connection()
    # ro'yxat: kalit nomi ("smtp.password") audit maskasiga tushmasin
    actions: list[dict[str, str]] = []
    for sd in integ.secrets:
        if sd.name in body.secrets:
            plain = body.secrets[sd.name]
            if plain is None:
                if clear_secret(conn, sd.name):
                    actions.append({"name": sd.name, "action": "cleared"})
            else:
                store_secret(conn, sd.name, plain, actor.user_id)
                actions.append({"name": sd.name, "action": "set"})
        elif endpoint_changed and clear_secret(conn, sd.name):
            actions.append({"name": sd.name, "action": "cleared_endpoint_changed"})
    rule = RULES.get(name)
    if rule is not None and (problem := rule(conn)) is not None:
        raise ValidationFailed(problem[0], fields=[problem[1]])  # get_db/sessiya rollback qiladi
    db.commit()  # commit-then-audit
    if changes or actions:
        log_event(meta, AuditAction.INTEGRATION_UPDATED, user_id=actor.user_id,
                  object_type="integration", object_id=name,
                  details={"changes": changes, "secrets": actions, "reason": reason})
        sysconfig.invalidate()
    return get_integration(db, name)


def _check_inline(db: Session, actor: AuthContext, name: str,
                  meta: ClientMeta) -> IntegrationCheckOut:
    """check_in == "api": probe shu jarayonda (egress api'da), natija core.integration_checks ga."""
    from app.ai.probe import API_PROBES

    probe = API_PROBES.get(name)
    if probe is None:
        raise NotFoundError()
    db.commit()  # probe davomida RLS/sessiya tranzaksiyasi ushlab turilmaydi
    try:
        code = probe()
    except Exception as exc:
        log.error("integration_probe_failed", name=name, error=type(exc).__name__)
        code = "error"
    row = db.execute(text(
        "INSERT INTO core.integration_checks (name, requested_by, status, code, finished_at) "
        f"VALUES (:n, :u, :s, :c, now()) RETURNING {_CHECK_COLS}"),
        {"n": name, "u": actor.user_id, "s": "ok" if code == "ok" else "failed",
         "c": code[:32]}).one()
    db.commit()
    log_event(meta, AuditAction.INTEGRATION_CHECK_REQUESTED, user_id=actor.user_id,
              object_type="integration", object_id=name, details={"check_id": row.id})
    return IntegrationCheckOut(**dict(row._mapping))


def request_check(db: Session, actor: AuthContext, name: str,
                  meta: ClientMeta) -> IntegrationCheckOut:
    integ = _integration(name)
    if integ.check_in != "worker":
        return _check_inline(db, actor, name, meta)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_integration_check_' || :n))"),
               {"n": name})
    row = db.execute(text(f"SELECT {_CHECK_COLS} FROM core.integration_checks WHERE name = :n "
                          "AND status IN ('pending', 'running') ORDER BY id DESC LIMIT 1"),
                     {"n": name}).first()
    if row is None:
        row = db.execute(text("INSERT INTO core.integration_checks (name, requested_by) "
                              f"VALUES (:n, :u) RETURNING {_CHECK_COLS}"),
                         {"n": name, "u": actor.user_id}).one()
        db.commit()
        log_event(meta, AuditAction.INTEGRATION_CHECK_REQUESTED, user_id=actor.user_id,
                  object_type="integration", object_id=name, details={"check_id": row.id})
    else:
        db.commit()
    return IntegrationCheckOut(**dict(row._mapping))


def get_check(db: Session, check_id: int) -> IntegrationCheckOut:
    row = db.execute(text(f"SELECT {_CHECK_COLS} FROM core.integration_checks WHERE id = :i"),
                     {"i": check_id}).first()
    if row is None:
        raise NotFoundError()
    return IntegrationCheckOut(**dict(row._mapping))
