"""ETL jurnali, qo'lda ishga tushirish (navbat orqali — worker bajaradi), buildlar (admin:etl)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin.dwh_schemas import (
    BuildOut,
    EtlErrorOut,
    EtlRequestOut,
    EtlRunDetail,
    EtlRunOut,
    EtlRunRequest,
    EtlStepOut,
    RollbackIn,
)
from app.admin.schemas import Page
from app.audit.service import AuditAction, log_event
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import NotFoundError, ValidationFailed
from app.core.request_meta import Meta
from app.dwh import builds
from app.etl.connectors import KNOWN_SOURCES

router = APIRouter(prefix="/admin", tags=["admin"])
DB = Annotated[Session, Depends(get_db)]
EtlAdmin = Annotated[AuthContext, Depends(require_perm(Perm.ADMIN_ETL))]
_RUN_COLS = ("id, source, mode, status, started_at, finished_at, window_from, window_to, "
             "rows_in, rows_upserted, build_id, triggered_by, error")


@router.get("/etl/runs")
def list_runs(
    ctx: EtlAdmin,
    db: DB,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Page[EtlRunOut]:
    total = db.execute(text("SELECT count(*) FROM core.etl_run")).scalar_one()
    rows = db.execute(text(f"SELECT {_RUN_COLS} FROM core.etl_run ORDER BY id DESC "
                           "LIMIT :l OFFSET :o"),
                      {"l": page_size, "o": (page - 1) * page_size}).all()
    items = [EtlRunOut(**dict(r._mapping)) for r in rows]
    return Page[EtlRunOut](items=items, total=int(total), page=page, page_size=page_size)


@router.get("/etl/runs/{run_id}")
def run_detail(run_id: int, ctx: EtlAdmin, db: DB) -> EtlRunDetail:
    row = db.execute(text(f"SELECT {_RUN_COLS} FROM core.etl_run WHERE id = :r"),
                     {"r": run_id}).first()
    if row is None:
        raise NotFoundError()
    steps = db.execute(text("SELECT name, status, started_at, finished_at, rows, detail "
                            "FROM core.etl_step WHERE run_id = :r ORDER BY id"),
                       {"r": run_id}).all()
    errors = db.execute(text("SELECT step, severity, target, src_id, code, message, created_at "
                             "FROM core.etl_error WHERE run_id = :r ORDER BY id LIMIT 500"),
                        {"r": run_id}).all()
    return EtlRunDetail(run=EtlRunOut(**dict(row._mapping)),
                        steps=[EtlStepOut(**dict(s._mapping)) for s in steps],
                        errors=[EtlErrorOut(**dict(e._mapping)) for e in errors])


@router.post("/etl/run", status_code=202)
def request_run(body: EtlRunRequest, ctx: EtlAdmin, db: DB, meta: Meta) -> EtlRequestOut:
    if body.source not in KNOWN_SOURCES:
        raise ValidationFailed("unknown_source", fields=["source"])
    if body.source == "synthetic" and get_settings().env == "prod":
        raise ValidationFailed("source_forbidden", fields=["source"])
    request_id = int(db.execute(
        text("INSERT INTO core.etl_requests (source, mode, requested_by) "
             "VALUES (:s, :m, :u) RETURNING id"),
        {"s": body.source, "m": body.mode, "u": ctx.user_id}).scalar_one())
    db.commit()  # commit-then-audit
    log_event(meta, AuditAction.ETL_RUN_REQUESTED, user_id=ctx.user_id, object_type="etl_request",
              object_id=request_id, details={"source": body.source, "mode": body.mode})
    return EtlRequestOut(request_id=request_id, status="pending")


def _build_out(info: builds.BuildInfo) -> BuildOut:
    return BuildOut(build_id=info.build_id, created_at=info.created_at, status=info.status,
                    load_id=info.load_id, published_at=info.published_at, active=info.active)


@router.get("/builds")
def list_builds(ctx: EtlAdmin, db: DB) -> list[BuildOut]:
    return [_build_out(b) for b in builds.list_builds(db.connection())]


@router.post("/builds/rollback")
def rollback_build(body: RollbackIn, ctx: EtlAdmin, db: DB, meta: Meta) -> BuildOut:
    conn = db.connection()
    previous = builds.active_build(conn)
    target = builds.rollback(conn, body.build_id)
    db.commit()  # commit-then-audit (keys_router.rotate_key)
    log_event(meta, AuditAction.BUILD_ROLLED_BACK, user_id=ctx.user_id, object_type="build",
              object_id=target, details={"from": previous, "to": target})
    return next(_build_out(b) for b in builds.list_builds(db.connection()) if b.build_id == target)
