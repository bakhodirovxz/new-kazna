"""Maker–checker: tasdiqlash / rad etish. Vazifalar ajratilishi servisda (`self_approval_forbidden`)
VA DB `CHECK` (`manual_batch_sod`) da. Tasdiq `dwh` ga yozmaydi: boshlarni belgilaydi va
`core.etl_requests (source='manual')` navbatiga so'rov qo'yadi -- ManualConnector/Runner yuklaydi.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, log_event
from app.auth.context import AuthContext
from app.core.errors import ConflictError, ForbiddenError, ValidationFailed
from app.core.request_meta import ClientMeta
from app.manual.entities import ENTITIES, ManualEntity
from app.manual.schemas import BatchOut, PublicationOut
from app.manual.store import (
    REASON_MAX,
    REASON_MIN,
    Row,
    audited,
    batch_entries,
    batch_out,
    canonical_hash,
    entity_or_404,
    load_batch,
    need,
    sane_text,
)
from app.manual.validate import assert_period_open


def _decidable(ctx: AuthContext, batch: Row, entity: ManualEntity, expected_version: int) -> None:
    need(ctx, entity, "approve")
    ctx.assert_branch(batch["branch_id"])
    if batch["created_by"] == ctx.user_id:
        raise ForbiddenError("self_approval_forbidden")
    if batch["status"] != "submitted":
        raise ValidationFailed("batch_not_editable", fields=["status"])
    if batch["version"] != expected_version:
        raise ConflictError("conflict_modified")


def _referenced(db: Session, entity: ManualEntity, code: str) -> bool:
    """Shu o'lchov kodiga havola qiluvchi tasdiqlangan, o'chirilmagan qo'lda fakt bormi."""
    for other in ENTITIES.values():
        for f in other.fields:
            if f.kind == "ref" and f.ref == entity.target and other.kind == "fact":
                found = db.execute(text(
                    "SELECT 1 FROM core.manual_head h JOIN core.manual_entry v "
                    "ON v.entry_id = h.entry_id AND v.version = h.approved_version "
                    "WHERE h.entity = :e AND NOT h.approved_deleted "
                    "AND v.payload ->> :f = :c LIMIT 1"),
                    {"e": other.id, "f": f.name, "c": code}).first()
                if found:
                    return True
    return False


def _queue_publication(db: Session, user_id: int) -> int:
    """Kutilayotgan `manual` so'rovi bo'lsa -- unga qo'shiladi (tasdiqlar birlashadi)."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_manual_publish'))"))
    pending = db.execute(text(
        "SELECT id FROM core.etl_requests WHERE source = 'manual' AND status = 'pending' "
        "ORDER BY id LIMIT 1")).scalar_one_or_none()
    if pending is not None:
        return int(pending)
    return int(db.execute(text(
        "INSERT INTO core.etl_requests (source, mode, requested_by) "
        "VALUES ('manual', 'full', :u) RETURNING id"), {"u": user_id}).scalar_one())


@audited(AuditAction.DATA_BATCH_APPROVED)
def approve_batch(db: Session, ctx: AuthContext, meta: ClientMeta, batch_id: int, *,
                  expected_version: int, comment: str | None = None) -> BatchOut:
    batch = load_batch(db, batch_id, lock=True)
    entity = entity_or_404(batch["entity"])
    _decidable(ctx, batch, entity, expected_version)
    rows = batch_entries(db, batch_id)
    if bytes(batch["content_hash"] or b"") != canonical_hash(rows):
        raise ConflictError("conflict_modified")  # yuborilgandan keyin mazmun o'zgargan
    if entity.kind == "fact":
        assert_period_open(db, entity, [r["payload"] for r in rows])
    for r in rows:
        if r["deleted"] and entity.kind == "dim" and _referenced(db, entity, r["code"]):
            raise ValidationFailed("reference_in_use", fields=["entry_id"], entry_id=r["entry_id"])
    request_id = _queue_publication(db, ctx.user_id)
    db.execute(text(
        "UPDATE core.manual_batch SET status = 'approved', decided_by = :u, decided_at = now(), "
        "decision_comment = :c, etl_request_id = :r, version = version + 1 WHERE batch_id = :b"),
        {"u": ctx.user_id, "c": sane_text(comment, "comment") or None, "r": request_id,
         "b": batch_id})
    for r in rows:
        done = db.execute(text(
            "UPDATE core.manual_head SET approved_version = :v, approved_deleted = :d, "
            "pending_batch_id = NULL, updated_at = now() "
            "WHERE entry_id = :e AND pending_batch_id = :b RETURNING entry_id"),
            {"v": r["version"], "d": r["deleted"], "e": r["entry_id"], "b": batch_id})
        if done.first() is None:
            raise ConflictError("conflict_modified")
    out = batch_out(load_batch(db, batch_id))
    db.commit()
    log_event(meta, AuditAction.DATA_BATCH_APPROVED, user_id=ctx.user_id,
              object_type="manual_batch", object_id=batch_id,
              details={"batch_id": batch_id, "entity": entity.id, "branch_id": out.branch_id,
                       "rows": out.rows, "content_hash": bytes(batch["content_hash"]).hex(),
                       "etl_request_id": request_id})
    return out


@audited(AuditAction.DATA_BATCH_REJECTED)
def reject_batch(db: Session, ctx: AuthContext, meta: ClientMeta, batch_id: int, *,
                 expected_version: int, comment: str | None) -> BatchOut:
    batch = load_batch(db, batch_id, lock=True)
    entity = entity_or_404(batch["entity"])
    _decidable(ctx, batch, entity, expected_version)
    cleaned = sane_text(comment, "comment")
    if not REASON_MIN <= len(cleaned) <= REASON_MAX:
        raise ValidationFailed("reason_required", fields=["comment"])
    db.execute(text("UPDATE core.manual_head SET pending_batch_id = NULL, updated_at = now() "
                    "WHERE pending_batch_id = :b"), {"b": batch_id})
    db.execute(text(
        "UPDATE core.manual_batch SET status = 'rejected', decided_by = :u, decided_at = now(), "
        "decision_comment = :c, version = version + 1 WHERE batch_id = :b"),
        {"u": ctx.user_id, "c": cleaned, "b": batch_id})
    out = batch_out(load_batch(db, batch_id))
    db.commit()
    log_event(meta, AuditAction.DATA_BATCH_REJECTED, user_id=ctx.user_id,
              object_type="manual_batch", object_id=batch_id,
              details={"batch_id": batch_id, "entity": entity.id, "branch_id": out.branch_id,
                       "rows": out.rows, "comment": cleaned,
                       "content_hash": bytes(batch["content_hash"] or b"").hex()})
    return out


def publication_status(db: Session, batch: BatchOut | Any) -> PublicationOut:
    """Tasdiqlangan paketning nashr holati: core.etl_requests -> core.etl_run."""
    if batch.status != "approved" or batch.etl_request_id is None:
        return PublicationOut(status="none")
    req = db.execute(text("SELECT status, run_id FROM core.etl_requests WHERE id = :i"),
                     {"i": batch.etl_request_id}).first()
    if req is None:
        return PublicationOut(status="none")
    if req.status == "pending":
        return PublicationOut(status="queued")
    if req.status == "running":
        return PublicationOut(status="running")
    if req.status == "failed" or req.run_id is None:
        return PublicationOut(status="failed")
    run = db.execute(text("SELECT status, build_id FROM core.etl_run WHERE id = :i"),
                     {"i": req.run_id}).first()
    if run is not None and run.status == "success" and run.build_id is not None:
        return PublicationOut(status="published", build_id=int(run.build_id))
    return PublicationOut(status="failed")
