"""`/api/v1/data/*`: qo'lda kiritish. Router darajasida: biror `data:*` yoki `audit:read`;
obyekt/bo'lim ruxsati va filial doirasi servisda tekshiriladi (deny-by-default)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.audit.service import AuditAction, log_event
from app.auth.context import AuthContext, Ctx, require_perm
from app.auth.permissions import ALL_DATA_PERMS, SECTION_TITLES, Perm, data_perm
from app.core import ratelimit
from app.core.db import DB
from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from app.core.logging import get_logger
from app.core.request_meta import Meta
from app.manual import approval, imports, store
from app.manual.entities import ENTITIES, FieldDef, ManualEntity
from app.manual.schemas import (
    BatchDetailOut,
    BatchIn,
    BatchOut,
    BatchUpdateIn,
    DecisionIn,
    EntityOut,
    FieldOut,
    HistoryOut,
    HistoryVersionOut,
    ItemIn,
    OptionOut,
    Page,
    RecordOut,
    SubmitIn,
    WithdrawIn,
)
from app.manual.validate import branch_scoped_sql
from app.sections.deps import SQ

log = get_logger(__name__)
router = APIRouter(
    prefix="/data",
    tags=["data"],
    dependencies=[Depends(require_perm(*ALL_DATA_PERMS, Perm.AUDIT_READ, any_of=True))],
)
PAGE_SIZE = 100
OPTION_LIMIT = 500  # FE ro'yxatni to'liq yuklab filtrlaydi; dim_bank 50 dan oshadi
# dim -> (kod ustuni, ko'rsatiladigan matn SQL); faqat koddan -- foydalanuvchi kiritmaydi.
_LABELS = {
    "dim_bank": "bank_name || coalesce(' …' || account_last4, '')",
    "dim_item": "name",
    "dim_branch": "name",
}


def _field_out(f: FieldDef) -> FieldOut:
    return FieldOut(
        name=f.name, kind=f.kind, title=f.title, required=f.required,
        lo=None if f.lo is None else str(f.lo), hi=None if f.hi is None else str(f.hi),
        options=[OptionOut(code=c, title=t) for c, t in f.options], ref=f.ref, unit=f.unit)


def _entity_out(e: ManualEntity, ctx: AuthContext) -> EntityOut:
    return EntityOut(
        id=e.id, section=e.section.value, section_title=SECTION_TITLES[e.section], title=e.title,
        kind=e.kind, layout=e.layout, grid=e.grid, fields=[_field_out(f) for f in e.fields],
        can_write=ctx.has(data_perm(e.section, "write")),
        can_approve=ctx.has(data_perm(e.section, "approve")))


def _readable(ctx: AuthContext, entity_id: str) -> ManualEntity:
    entity = store.entity_or_404(entity_id)
    if not (ctx.has(data_perm(entity.section, "write"))
            or ctx.has(data_perm(entity.section, "approve"))):
        raise ForbiddenError()
    return entity


@router.get("/entities")
def list_entities(ctx: Ctx) -> list[EntityOut]:
    return [_entity_out(e, ctx) for e in ENTITIES.values()
            if ctx.has(data_perm(e.section, "write")) or ctx.has(data_perm(e.section, "approve"))]


@router.get("/entities/{entity_id}/records")
def list_records(
    entity_id: str, ctx: Ctx, db: DB, sq: SQ,
    status: Annotated[Literal["active", "pending", "deleted"] | None, Query()] = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
) -> Page[RecordOut]:
    entity = _readable(ctx, entity_id)
    where = ["h.entity = :e", "(h.pending_batch_id IS NOT NULL OR h.approved_version IS NOT NULL)"]
    params: dict[str, Any] = {"e": entity.id}
    if sq.br is not None:
        where.append("h.branch_id = :br")
        params["br"] = sq.br
    field = entity.date_field
    if field is not None and entity.kind == "fact":
        per = sq.period()
        where.append("v.payload ->> :df BETWEEN :d1 AND :d2")
        params |= {"df": field.name, "d1": per.date_from.isoformat(),
                   "d2": per.date_to.isoformat()}
    state = ("CASE WHEN h.pending_batch_id IS NOT NULL THEN 'pending' "
             "WHEN h.approved_deleted THEN 'deleted' ELSE 'active' END")
    where.append(f"{state} = :st" if status else f"{state} <> 'deleted'")
    if status:
        params["st"] = status
    cond = " AND ".join(where)
    join = ("FROM core.manual_head h JOIN core.manual_entry v ON v.entry_id = h.entry_id "
            "AND v.version = CASE WHEN h.pending_batch_id IS NOT NULL THEN h.version "
            "ELSE h.approved_version END")
    # nosemgrep: avoid-sqlalchemy-text -- shartlar koddan, qiymatlar parametr
    total = db.execute(text(f"SELECT count(*) {join} WHERE {cond}"), params).scalar_one()
    rows = db.execute(text(  # nosemgrep: avoid-sqlalchemy-text
        f"SELECT h.entry_id, h.version, h.branch_id, h.pending_batch_id, {state} AS state, "
        f"v.payload, v.masks {join} WHERE {cond} ORDER BY h.entry_id DESC LIMIT :n OFFSET :o"),
        {**params, "n": PAGE_SIZE, "o": (page - 1) * PAGE_SIZE}).mappings()
    items = [RecordOut(entry_id=r["entry_id"], version=r["version"], branch_id=r["branch_id"],
                       values=r["payload"], masks=r["masks"], status=r["state"],
                       pending_batch_id=r["pending_batch_id"]) for r in rows]
    return Page[RecordOut](items=items, total=int(total), page=page)


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("/entities/{entity_id}/options/{field}")
def field_options(
    entity_id: str, field: str, ctx: Ctx, db: DB,
    q: Annotated[str, Query(max_length=64)] = "",
    br: Annotated[int | None, Query(ge=1)] = None,
) -> list[OptionOut]:
    entity = store.entity_or_404(entity_id)
    store.need(ctx, entity, "write")
    f = next((x for x in entity.fields if x.name == field and x.kind == "ref"), None)
    if f is None or f.ref not in _LABELS:
        raise NotFoundError()
    ctx.assert_branch(br)
    where = f" AND {f.ref_where}" if f.ref_where else ""
    found: dict[str, str] = {}
    # nosemgrep: avoid-sqlalchemy-text -- jadval/ustun/shart koddan, qiymat parametr
    for code, title in db.execute(text(
            f"SELECT code, {_LABELS[f.ref]} FROM dwh.{f.ref} "  # noqa: S608
            f"WHERE (code ILIKE :q OR {_LABELS[f.ref]} ILIKE :q){where}"
            f"{branch_scoped_sql(f)} ORDER BY code LIMIT :n"),
            {"q": _like(q), "n": OPTION_LIMIT, **({"br": br} if f.branch_scoped else {})}).all():
        found[code] = title
    owners = [e.id for e in ENTITIES.values() if e.kind == "dim" and e.target == f.ref]
    if owners and not f.ref_where:
        manual = db.execute(text(
            "SELECT code, title FROM (SELECT h.code, h.branch_id, "
            "coalesce(v.payload ->> 'bank_name', h.code) || "
            "coalesce(' ' || (v.masks ->> 'account_number'), '') AS title "
            "FROM core.manual_head h JOIN core.manual_entry v ON v.entry_id = h.entry_id "
            "AND v.version = h.approved_version "
            "WHERE h.entity = ANY(:o) AND NOT h.approved_deleted) m "
            "WHERE (code ILIKE :q OR title ILIKE :q) "
            "AND (CAST(:br AS integer) IS NULL OR branch_id = :br) ORDER BY code LIMIT :n"),
            {"o": owners, "q": _like(q), "br": br, "n": OPTION_LIMIT}).all()
        for code, title in manual:
            found.setdefault(code, title)
    return [OptionOut(code=c, title=t) for c, t in sorted(found.items())[:OPTION_LIMIT]]


@router.get("/records/{entry_id}/history")
def record_history(entry_id: int, ctx: Ctx, db: DB) -> HistoryOut:
    head = db.execute(text("SELECT entity FROM core.manual_head WHERE entry_id = :e"),
                      {"e": entry_id}).first()
    if head is None:  # RLS: begona filial yozuvi ham shu yerda -- 404
        raise NotFoundError()
    entity = store.entity_or_404(head.entity)
    if not (ctx.has(Perm.AUDIT_READ.value) or ctx.has(data_perm(entity.section, "write"))
            or ctx.has(data_perm(entity.section, "approve"))):
        raise ForbiddenError()
    rows = db.execute(text(
        "SELECT v.version, v.batch_id, b.status, v.created_at, v.deleted, v.payload, v.masks, "
        "b.reason, b.decided_at, cu.full_name AS created_by_name, du.full_name AS decided_by_name "
        "FROM core.manual_entry v JOIN core.manual_batch b ON b.batch_id = v.batch_id "
        "LEFT JOIN core.users cu ON cu.id = v.created_by "
        "LEFT JOIN core.users du ON du.id = b.decided_by "
        "WHERE v.entry_id = :e ORDER BY v.version DESC"), {"e": entry_id}).mappings()
    return HistoryOut(versions=[HistoryVersionOut(
        version=r["version"], batch_id=r["batch_id"], batch_status=r["status"],
        created_by_name=r["created_by_name"], created_at=r["created_at"],
        decided_by_name=r["decided_by_name"], decided_at=r["decided_at"], reason=r["reason"],
        deleted=r["deleted"], values=r["payload"], masks=r["masks"]) for r in rows])


@router.post("/batches", status_code=201)
def create_batch(body: BatchIn, ctx: Ctx, db: DB, meta: Meta) -> BatchOut:
    return store.create_batch(
        db, ctx, meta, entity_id=body.entity, branch_id=body.branch_id, origin=body.origin,
        items=body.items, submit=body.submit, reason=body.reason)


@router.put("/batches/{batch_id}")
def update_batch(batch_id: int, body: BatchUpdateIn, ctx: Ctx, db: DB, meta: Meta) -> BatchOut:
    return store.update_batch(db, ctx, meta, batch_id, expected_version=body.expected_version,
                              items=body.items)


@router.post("/batches/{batch_id}/submit")
def submit_batch(batch_id: int, body: SubmitIn, ctx: Ctx, db: DB, meta: Meta) -> BatchOut:
    return store.submit_batch(db, ctx, meta, batch_id, expected_version=body.expected_version,
                              reason=body.reason)


@router.post("/batches/{batch_id}/withdraw")
def withdraw_batch(batch_id: int, body: WithdrawIn, ctx: Ctx, db: DB, meta: Meta) -> BatchOut:
    return store.withdraw_batch(db, ctx, meta, batch_id, expected_version=body.expected_version)


@router.post("/batches/{batch_id}/approve")
def approve_batch(batch_id: int, body: DecisionIn, ctx: Ctx, db: DB, meta: Meta) -> BatchOut:
    return approval.approve_batch(db, ctx, meta, batch_id,
                                  expected_version=body.expected_version, comment=body.comment)


@router.post("/batches/{batch_id}/reject")
def reject_batch(batch_id: int, body: DecisionIn, ctx: Ctx, db: DB, meta: Meta) -> BatchOut:
    return approval.reject_batch(db, ctx, meta, batch_id,
                                 expected_version=body.expected_version, comment=body.comment)


@router.get("/batches")
def list_batches(
    ctx: Ctx, db: DB, box: Literal["mine", "inbox"] = "mine",
    status: Annotated[
        Literal["draft", "submitted", "approved", "rejected", "withdrawn", "failed"] | None,
        Query()] = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
) -> Page[BatchOut]:
    return store.list_batches(db, ctx, box=box, status=status, page=page)


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, ctx: Ctx, db: DB) -> BatchDetailOut:
    out = store.get_batch(db, ctx, batch_id)
    return out



# --- shablon va fayldan import -------------------------------------------------------------



def _writable(ctx: AuthContext, entity_id: str) -> ManualEntity:
    entity = store.entity_or_404(entity_id)
    store.need(ctx, entity, "write")
    return entity


def _download(body: bytes, media: str, name: str) -> Response:
    return Response(body, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.get("/entities/{entity_id}/template.csv")
def template_csv(entity_id: str, ctx: Ctx) -> Response:
    entity = _writable(ctx, entity_id)
    return _download(imports.template_csv(entity), "text/csv; charset=utf-8",
                     f"{entity.id}.csv")


@router.get("/entities/{entity_id}/template.xlsx")
def template_xlsx(entity_id: str, ctx: Ctx) -> Response:
    entity = _writable(ctx, entity_id)
    return _download(imports.template_xlsx(entity), imports.XLSX_TYPE, f"{entity.id}.xlsx")


def _remap(exc: AppError, lines: list[int]) -> AppError:
    """ItemIn indeksi (1 = birinchi ma'lumot qatori) -> fayl qatori; xato shakli bir joyda (M8)."""
    rows = [{**r, "row": lines[r["row"] - 1] if 0 < r["row"] <= len(lines) else r["row"]}
            for r in exc.params.get("rows", []) if isinstance(r, dict)]
    params = {**exc.params, "rows": rows}
    if isinstance(exc, ValidationFailed):
        return ValidationFailed("import_invalid", **params)
    return type(exc)(exc.code, **params)


@router.post("/entities/{entity_id}/import", status_code=201)
async def import_file(
    entity_id: str, request: Request, ctx: Ctx, db: DB, meta: Meta,
    branch_id: Annotated[int, Query(ge=1)],
    # tana parametri: FastAPI tanani bog'liqliklardan (DB slot!) OLDIN o'qiydi -- sekin yuklash
    # DB ulanishini ushlab turmaydi (review I5)
    body: Annotated[bytes, Body(media_type="application/octet-stream")],
) -> BatchOut:
    entity = _writable(ctx, entity_id)
    ctx.assert_branch(branch_id)
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    name = imports.safe_name(request.headers.get("x-file-name", ""))
    digest = imports.file_digest(body)

    def rejected(exc: AppError) -> None:
        log_event(meta, AuditAction.DATA_IMPORT_REJECTED, user_id=ctx.user_id, result="fail",
                  object_type="manual_entity", object_id=entity.id,
                  details={"entity": entity.id, "branch_id": branch_id, "size": len(body),
                           "error": exc.code, "file_name": name, "hmac": digest.hex()})

    if media not in (imports.CSV_TYPE, imports.XLSX_TYPE):
        exc = ValidationFailed("unsupported_file")
        rejected(exc)
        raise exc
    ratelimit.check("data_import", str(ctx.user_id), ratelimit.DATA_IMPORT_PER_USER)

    def work() -> BatchOut:
        lines: list[int] = []
        try:
            items, lines = imports.parse_upload(entity, body, media)
            out = store.create_batch(
                db, ctx, meta, entity_id=entity.id, branch_id=branch_id, origin="import",
                items=[ItemIn(values=r) for r in items],
                file_meta={"name": name, "sha256": digest})
        except (ValidationFailed, ConflictError) as exc:
            if isinstance(exc, imports.FormatErrors):  # format + spravochnik xatolari bir yo'la
                try:
                    exc = imports.with_reference_errors(db, entity, branch_id, exc)
                except Exception as err:  # tekshiruv yiqilsa ham rad etish auditga tushadi
                    log.error("import_reference_check_failed", error=type(err).__name__)
                    db.rollback()
            new = _remap(exc, lines) if lines and exc.params.get("rows") else exc
            rejected(new)
            raise new from None
        except AppError as exc:  # import_busy va h.k.
            rejected(exc)
            raise
        log_event(meta, AuditAction.DATA_IMPORTED, user_id=ctx.user_id,
                  object_type="manual_batch", object_id=out.batch_id,
                  details={"batch_id": out.batch_id, "entity": entity.id, "file_name": name,
                           "hmac": digest.hex(), "size": len(body), "rows": out.rows})
        return out

    return await run_in_threadpool(work)
