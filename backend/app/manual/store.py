"""«Ввод данных» paket servisi: yaratish, draft, yuborish, qaytarib olish.

Qoidalar: yozuv faqat `core.manual_*` ga (RLS FORCE, `ugk_app`) yoziladi; `dwh`/`mart` ga
hech qachon. Sezgir maydon (hisob raqami, INN) AES-256-GCM, AAD `core.manual_entry.{col}:{id}`;
payload, audit va javobda faqat niqob. Commit-then-audit (`etl_router` naqshi): audit
`log_event` alohida ulanishda yoziladi, shuning uchun RLS `SET LOCAL` commitdan keyin kerak emas.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Literal, TypeVar

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, log_event
from app.auth.context import AuthContext
from app.auth.permissions import data_perm
from app.core import keystore, ratelimit
from app.core.crypto import Purpose
from app.core.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ScopeViolationError,
    ValidationFailed,
)
from app.core.request_meta import ClientMeta
from app.manual.entities import ENTITIES, FieldDef, ManualEntity, business_key
from app.manual.schemas import (
    MAX_IMPORT_ROWS,
    MAX_ITEMS,
    BatchDetailOut,
    BatchOut,
    ChangeOut,
    ItemIn,
    Page,
)
from app.manual.validate import assert_period_open, check_items

__all__ = [
    "ItemIn",
    "audited",
    "create_batch",
    "get_batch",
    "list_batches",
    "submit_batch",
    "update_batch",
    "withdraw_batch",
]

PAGE_SIZE = 50
CHANGES_IN_AUDIT = 100
REASON_MIN, REASON_MAX = 5, 500
_ENC_COLUMN = {Purpose.BANK: "bank_enc", Purpose.PII: "pii_enc"}
F = TypeVar("F", bound=Callable[..., Any])
Row = Mapping[Any, Any]  # SQLAlchemy RowMapping yoki dict


# --- umumiy yordamchilar ---------------------------------------------------------------


def audited(action: AuditAction) -> Callable[[F], F]:
    """Muvaffaqiyatsiz amalni ham audit qiladi (ruxsat -> `denied`, qolgani -> `fail`);
    xato matni/qiymatlari auditga tushmaydi -- faqat kod. ScopeViolation global handlerda."""

    def deco(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(db: Session, ctx: AuthContext, meta: ClientMeta, *args: Any, **kw: Any) -> Any:
            try:
                return fn(db, ctx, meta, *args, **kw)
            except AppError as exc:
                if isinstance(exc, ScopeViolationError) or exc.code == "rate_limited":
                    raise
                db.rollback()
                first = args[0] if args else None
                batch_id = kw.get("batch_id", first if isinstance(first, int) else None)
                log_event(meta, action, user_id=ctx.user_id,
                          result="denied" if isinstance(exc, ForbiddenError) else "fail",
                          object_type="manual_batch", object_id=batch_id,
                          details={"error": exc.code, "entity": kw.get("entity_id")})
                raise

        return wrapper  # type: ignore[return-value]

    return deco


def entity_or_404(entity_id: str) -> ManualEntity:
    entity = ENTITIES.get(entity_id)
    if entity is None:
        raise NotFoundError()
    return entity


def need(ctx: AuthContext, entity: ManualEntity, action: Literal["write", "approve"]) -> None:
    if not ctx.has(data_perm(entity.section, action)):
        raise ForbiddenError()


_BATCH_SELECT = "SELECT * FROM core.manual_batch WHERE batch_id = :i"
_BATCH_LOCK = _BATCH_SELECT + " FOR UPDATE"


def load_batch(db: Session, batch_id: int, *, lock: bool = False) -> Row:
    sql = _BATCH_LOCK if lock else _BATCH_SELECT
    row = db.execute(text(sql), {"i": batch_id}).mappings().first()  # RLS: begona filial -- yo'q
    if row is None:
        raise NotFoundError()
    return row


def batch_out(row: Row) -> BatchOut:
    return BatchOut(**{k: row[k] for k in BatchOut.model_fields})


def _stamp(db: Session, batch_id: int) -> BatchOut:
    return batch_out(load_batch(db, batch_id))


def _mask(value: str) -> str:
    return "…" + value[-4:]


def _scalar(f: FieldDef, value: Any) -> Any:
    if value is None:
        return None
    if f.kind == "money":
        return format(Decimal(value).quantize(Decimal("0.01")), "f")
    if f.kind in ("volume", "decimal"):
        return format(Decimal(value).quantize(Decimal("0.001")), "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def public_values(payload: Row, masks: Mapping[str, str]) -> dict[str, Any]:
    """Audit/diff ko'rinishi: sezgir maydon -- {"changed": true, "mask": "…1234"}."""
    out = dict(payload)
    for name, mask in masks.items():
        out[name] = {"changed": True, "mask": mask}
    return out


def canonical_hash(rows: Sequence[Row]) -> bytes:
    """Paket mazmuni SHA-256. Shifrlangan baytlar kirmaydi (kalit aylantirish blobni
    o'zgartiradi): sezgir maydon niqob va head.code (HMAC) orqali bog'lanadi."""
    body = [
        [r["entry_id"], r["version"], r["deleted"], r["payload"], r["masks"], r["code"],
         r["business_key"]]
        for r in sorted(rows, key=lambda r: r["entry_id"])
    ]
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).digest()


def batch_entries(db: Session, batch_id: int) -> list[Row]:
    return list(db.execute(text(
        "SELECT e.id, e.entry_id, e.version, e.deleted, e.payload, e.masks, h.code, "
        "h.business_key, h.approved_version, h.entity "
        "FROM core.manual_entry e JOIN core.manual_head h ON h.entry_id = e.entry_id "
        "WHERE e.batch_id = :b ORDER BY e.entry_id"), {"b": batch_id}).mappings())


def _prior(db: Session, entry_id: int, version: int) -> Row | None:
    """Paketdan OLDINGI tasdiqlangan holat: bu versiyadan kichik eng so'nggi tasdiqlangan versiya
    (tasdiqlangach `approved_version` paketning o'ziga ko'chadi -- diff o'ziga solishtirilmasin)."""
    return db.execute(text(
        "SELECT p.payload, p.masks FROM core.manual_entry p "
        "JOIN core.manual_batch b ON b.batch_id = p.batch_id "
        "WHERE p.entry_id = :e AND p.version < :v AND b.status = 'approved' "
        "ORDER BY p.version DESC LIMIT 1"), {"e": entry_id, "v": version}).mappings().first()


def changes(db: Session, entity: ManualEntity, batch_id: int) -> list[ChangeOut]:
    out = []
    for r in batch_entries(db, batch_id):
        prev = _prior(db, r["entry_id"], r["version"])
        op: Literal["add", "change", "delete"] = (
            "delete" if r["deleted"] else "add" if prev is None else "change")
        out.append(ChangeOut(
            entry_id=r["entry_id"], version=r["version"], op=op,
            before=None if prev is None else public_values(prev["payload"], prev["masks"]),
            after=None if r["deleted"] else public_values(r["payload"], r["masks"])))
    return out


_BAD_TEXT = re.compile("[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]")


def sane_text(value: str | None, field: str) -> str:
    """Erkin matn (sabab/izoh): boshqaruv va bidi belgilarisiz (audit/tarixda ko'rsatiladi)."""
    cleaned = (value or "").strip()
    if _BAD_TEXT.search(cleaned):
        raise ValidationFailed("invalid_value", fields=[field])
    return cleaned


def clean_reason(reason: str | None) -> str:
    cleaned = sane_text(reason, "reason")
    if not REASON_MIN <= len(cleaned) <= REASON_MAX:
        raise ValidationFailed("reason_required", fields=["reason"])
    return cleaned


# --- yozuv (versiya) qo'shish -------------------------------------------------------------


def _payload_of(entity: ManualEntity, values: Row) -> dict[str, Any]:
    return {f.name: _scalar(f, values.get(f.name)) for f in entity.fields
            if f.kind != "secret" and values.get(f.name) is not None}


def _latest(db: Session, entry_id: int) -> Row | None:
    return db.execute(text(
        "SELECT id, version, payload, masks, bank_enc, pii_enc FROM core.manual_entry "
        "WHERE entry_id = :e ORDER BY version DESC LIMIT 1"), {"e": entry_id}).mappings().first()


def _decrypt_secret(f: FieldDef, prev: Row) -> str | None:
    assert f.purpose is not None
    col = _ENC_COLUMN[f.purpose]
    blob = prev[col]
    if blob is None:
        return None
    return keystore.decrypt_str(f.purpose, bytes(blob), f"core.manual_entry.{col}:{prev['id']}")


def _insert_version(
    db: Session, ctx: AuthContext, entity: ManualEntity, *, head_id: int, version: int,
    batch_id: int, branch_id: int, values: Row, deleted: bool,
    prev: Row | None = None,
) -> None:
    row_id = db.execute(text("SELECT nextval('core.manual_entry_id_seq')")).scalar_one()
    enc: dict[str, bytes | None] = {"bank_enc": None, "pii_enc": None}
    masks: dict[str, str] = {}
    if deleted and prev is not None:  # tombstone: oldingi qiymatning nusxasi
        payload = dict(prev["payload"])
        for f in entity.secrets:
            plain = _decrypt_secret(f, prev)
            values = {**values, f.name: plain}
    else:
        payload = _payload_of(entity, values)
    for f in entity.secrets:
        plain = values.get(f.name)
        if plain:
            assert f.purpose is not None
            col = _ENC_COLUMN[f.purpose]
            enc[col] = keystore.encrypt_str(f.purpose, str(plain),
                                            f"core.manual_entry.{col}:{row_id}")
            masks[f.name] = _mask(str(plain))
    db.execute(text(
        "INSERT INTO core.manual_entry (id, entry_id, version, batch_id, branch_id, payload, "
        "bank_enc, pii_enc, masks, deleted, created_by) VALUES (:id, :e, :v, :b, :br, "
        "CAST(:p AS jsonb), :be, :pe, CAST(:m AS jsonb), :d, :u)"),
        {"id": row_id, "e": head_id, "v": version, "b": batch_id, "br": branch_id,
         "p": json.dumps(payload, ensure_ascii=False), "be": enc["bank_enc"],
         "pe": enc["pii_enc"], "m": json.dumps(masks, ensure_ascii=False), "d": deleted,
         "u": ctx.user_id})
    db.execute(text(
        "UPDATE core.manual_head SET version = :v, pending_batch_id = :b, updated_at = now() "
        "WHERE entry_id = :e"), {"v": version, "b": batch_id, "e": head_id})


def _discard_drafts(db: Session, batch_id: int) -> dict[int, int]:
    """Draft paket qatorlarini olib tashlaydi, boshlarni oldingi holatga qaytaradi.
    Qaytaradi: {entry_id: olib tashlangan versiya} (UI ko'rgan `expected_version`)."""
    rows = db.execute(text(
        "SELECT e.entry_id, e.version FROM core.manual_entry e WHERE e.batch_id = :b "
        "ORDER BY e.entry_id"), {"b": batch_id}).all()
    for entry_id, _ in rows:
        db.execute(text("SELECT 1 FROM core.manual_head WHERE entry_id = :e FOR UPDATE"),
                   {"e": entry_id})
    db.execute(text("DELETE FROM core.manual_entry WHERE batch_id = :b"), {"b": batch_id})
    for entry_id, _ in rows:
        db.execute(text(
            "UPDATE core.manual_head SET pending_batch_id = NULL, updated_at = now(), "
            "version = coalesce((SELECT max(version) FROM core.manual_entry "
            "WHERE entry_id = :e), 0) WHERE entry_id = :e"), {"e": entry_id})
    return {int(e): int(v) for e, v in rows}


# --- tayyorlash: qulflar, optimistik tekshiruv, tekshiruv ------------------------------------


class _Planned:
    __slots__ = ("delete", "head", "item", "prev", "values")

    def __init__(self, item: ItemIn, head: Row | None,
                 prev: Row | None) -> None:
        self.item, self.head, self.prev = item, head, prev
        self.delete = item.delete
        self.values: dict[str, Any] = {}


def _raise_item_errors(errors: list[dict[str, Any]]) -> None:
    raise ValidationFailed(
        errors[0]["code"], rows=errors[:200], fields=sorted({e["field"] for e in errors}))


def _prepare(db: Session, entity: ManualEntity, branch_id: int, items: Sequence[ItemIn],
             *, own_batch: int | None, seen_versions: Mapping[int, int]) -> list[_Planned]:
    planned: list[_Planned] = []
    seen_ids: set[int] = set()
    errors: list[dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        head = prev = None
        if item.entry_id is not None:
            if item.entry_id in seen_ids:
                errors.append({"row": idx, "field": "entry_id", "code": "duplicate_record"})
                continue
            seen_ids.add(item.entry_id)
            head = db.execute(text("SELECT * FROM core.manual_head WHERE entry_id = :e FOR UPDATE"),
                              {"e": item.entry_id}).mappings().first()
            if head is None or head["entity"] != entity.id:
                raise NotFoundError()
            if head["branch_id"] != branch_id:
                errors.append({"row": idx, "field": "branch_code", "code": "invalid_value"})
                continue
            allowed = {head["version"], seen_versions.get(item.entry_id, -1)}
            if item.expected_version is None or item.expected_version not in allowed:
                raise ConflictError("conflict_modified", entry_id=item.entry_id)
            if head["pending_batch_id"] not in (None, own_batch):
                raise ConflictError("pending_change", entry_id=item.entry_id)
            prev = _latest(db, item.entry_id)
            if item.delete and (head["approved_version"] is None or head["approved_deleted"]):
                errors.append({"row": idx, "field": "entry_id", "code": "invalid_value"})
                continue
        elif item.delete:
            errors.append({"row": idx, "field": "entry_id", "code": "invalid_value"})
            continue
        plan = _Planned(item, head, prev)
        if not item.delete:
            plan.values = dict(item.values)
            if prev is not None:  # sezgir maydon bo'sh qoldirilsa -- o'zgarmaydi (write-only)
                for f in entity.secrets:
                    if not plan.values.get(f.name):
                        plain = _decrypt_secret(f, prev)
                        if plain:
                            plan.values[f.name] = plain
        planned.append(plan)

    to_check = [(i, p) for i, p in enumerate(planned, start=1) if not p.delete]
    models, item_errors = check_items(db, entity, branch_id, [p.values for _, p in to_check])
    errors += [{**e, "row": to_check[e["row"] - 1][0]} for e in item_errors]
    if not errors:
        from app.manual.validate import to_values

        for (idx, p), model in zip(to_check, models, strict=True):
            p.values = to_values(model)
            if p.head is not None and business_key(entity, p.values) != p.head["business_key"]:
                errors.append({"row": idx, "field": entity.grain[0].split(":")[0],
                               "code": "invalid_value"})
    if errors:
        _raise_item_errors(errors)
    assert_period_open(db, entity, [p.prev["payload"] for p in planned if p.delete and p.prev])
    return planned


def _apply(db: Session, ctx: AuthContext, entity: ManualEntity, batch_id: int, branch_id: int,
           planned: Sequence[_Planned]) -> None:
    for p in planned:
        if p.head is not None:
            _insert_version(db, ctx, entity, head_id=p.head["entry_id"],
                            version=p.head["version"] + 1, batch_id=batch_id,
                            branch_id=branch_id, values=p.values, deleted=p.delete, prev=p.prev)
            continue
        key = business_key(entity, p.values)
        head_id = db.execute(text(
            "INSERT INTO core.manual_head (entity, branch_id, business_key) "
            "VALUES (:e, :b, :k) ON CONFLICT (entity, business_key) DO NOTHING "
            "RETURNING entry_id"), {"e": entity.id, "b": branch_id, "k": key}).scalar_one_or_none()
        version = 1
        if head_id is None:
            old = db.execute(text(
                "SELECT entry_id, version, approved_version, pending_batch_id "
                "FROM core.manual_head WHERE entity = :e AND business_key = :k FOR UPDATE"),
                {"e": entity.id, "k": key}).mappings().first()
            if old is None:  # begona filial yozuvi (RLS) -- mavjudligi oshkor qilinmaydi
                raise ConflictError("duplicate_record")
            if old["approved_version"] is not None or old["pending_batch_id"] is not None:
                raise ConflictError("duplicate_record", entry_id=old["entry_id"])
            head_id, version = old["entry_id"], old["version"] + 1  # tashlab ketilgan bosh
        if entity.kind == "dim":
            code = (entity.code_fn(p.values) if entity.code_fn
                    else f"{entity.code_prefix}-{head_id}")
            try:
                with db.begin_nested():
                    db.execute(text("UPDATE core.manual_head SET code = :c WHERE entry_id = :e"),
                               {"c": code, "e": head_id})
            except IntegrityError as exc:
                raise ConflictError("duplicate_record") from exc
        _insert_version(db, ctx, entity, head_id=head_id, version=version, batch_id=batch_id,
                        branch_id=branch_id, values=p.values, deleted=False)


# --- ommaviy servis ------------------------------------------------------------------------


@audited(AuditAction.DATA_BATCH_SAVED)
def create_batch(
    db: Session, ctx: AuthContext, meta: ClientMeta, *, entity_id: str, branch_id: int,
    origin: Literal["form", "grid", "import"], items: Sequence[ItemIn], submit: bool = False,
    reason: str | None = None, file_meta: Row | None = None,
) -> BatchOut:
    entity = entity_or_404(entity_id)
    need(ctx, entity, "write")
    ctx.assert_branch(branch_id)
    ratelimit.check("data_write", str(ctx.user_id), ratelimit.data_write_per_user())
    if not 1 <= len(items) <= (MAX_IMPORT_ROWS if origin == "import" else MAX_ITEMS):
        raise ValidationFailed("invalid_value", fields=["items"])
    planned = _prepare(db, entity, branch_id, items, own_batch=None, seen_versions={})
    file_meta = file_meta or {}
    batch_id = db.execute(text(
        "INSERT INTO core.manual_batch (entity, branch_id, origin, rows, created_by, file_name, "
        "file_sha256) VALUES (:e, :b, :o, :n, :u, :fn, :fh) RETURNING batch_id"),
        {"e": entity.id, "b": branch_id, "o": origin, "n": len(planned), "u": ctx.user_id,
         "fn": file_meta.get("name"), "fh": file_meta.get("sha256")}).scalar_one()
    _apply(db, ctx, entity, batch_id, branch_id, planned)
    if submit:
        return _submit(db, ctx, meta, entity, load_batch(db, batch_id, lock=True), reason)
    out = _stamp(db, batch_id)
    db.commit()
    log_event(meta, AuditAction.DATA_BATCH_SAVED, user_id=ctx.user_id, object_type="manual_batch",
              object_id=batch_id,
              details={"batch_id": batch_id, "entity": entity.id, "branch_id": branch_id,
                       "rows": out.rows, "origin": origin})
    return out


def _creator_draft(ctx: AuthContext, batch: Row, expected_version: int) -> None:
    if batch["created_by"] != ctx.user_id:
        raise ForbiddenError()
    if batch["status"] != "draft":
        raise ValidationFailed("batch_not_editable", fields=["status"])
    if batch["version"] != expected_version:
        raise ConflictError("conflict_modified")


@audited(AuditAction.DATA_BATCH_SAVED)
def update_batch(db: Session, ctx: AuthContext, meta: ClientMeta, batch_id: int, *,
                 expected_version: int, items: Sequence[ItemIn]) -> BatchOut:
    batch = load_batch(db, batch_id, lock=True)
    entity = entity_or_404(batch["entity"])
    need(ctx, entity, "write")
    ctx.assert_branch(batch["branch_id"])
    _creator_draft(ctx, batch, expected_version)
    ratelimit.check("data_write", str(ctx.user_id), ratelimit.data_write_per_user())
    if not 1 <= len(items) <= MAX_ITEMS:
        raise ValidationFailed("invalid_value", fields=["items"])
    seen = _discard_drafts(db, batch_id)
    planned = _prepare(db, entity, batch["branch_id"], items, own_batch=batch_id,
                       seen_versions=seen)
    _apply(db, ctx, entity, batch_id, batch["branch_id"], planned)
    db.execute(text("UPDATE core.manual_batch SET rows = :n, version = version + 1 "
                    "WHERE batch_id = :b"), {"n": len(planned), "b": batch_id})
    out = _stamp(db, batch_id)
    db.commit()
    log_event(meta, AuditAction.DATA_BATCH_SAVED, user_id=ctx.user_id, object_type="manual_batch",
              object_id=batch_id,
              details={"batch_id": batch_id, "entity": entity.id, "rows": out.rows,
                       "branch_id": out.branch_id, "origin": out.origin})
    return out


def _submit(db: Session, ctx: AuthContext, meta: ClientMeta, entity: ManualEntity,
            batch: Row, reason: str | None) -> BatchOut:
    rows = batch_entries(db, batch["batch_id"])
    if not rows:
        raise ValidationFailed("invalid_value", fields=["items"])
    assert_period_open(db, entity, [r["payload"] for r in rows])  # tombstone ham
    corrections = any(r["approved_version"] is not None for r in rows)
    cleaned = clean_reason(reason) if corrections else sane_text(reason, "reason") or None
    digest = canonical_hash(rows)
    diff = changes(db, entity, batch["batch_id"])
    db.execute(text(
        "UPDATE core.manual_batch SET status = 'submitted', submitted_at = now(), "
        "content_hash = :h, reason = :r, version = version + 1 WHERE batch_id = :b"),
        {"h": digest, "r": cleaned, "b": batch["batch_id"]})
    out = _stamp(db, batch["batch_id"])
    db.commit()
    log_event(meta, AuditAction.DATA_BATCH_SUBMITTED, user_id=ctx.user_id,
              object_type="manual_batch", object_id=out.batch_id,
              details={"batch_id": out.batch_id, "entity": entity.id, "branch_id": out.branch_id,
                       "rows": out.rows, "content_hash": digest.hex(),
                       "changes": [c.model_dump() for c in diff[:CHANGES_IN_AUDIT]],
                       "truncated": len(diff) > CHANGES_IN_AUDIT,
                       **({"reason": cleaned} if cleaned else {})})
    return out


@audited(AuditAction.DATA_BATCH_SUBMITTED)
def submit_batch(db: Session, ctx: AuthContext, meta: ClientMeta, batch_id: int, *,
                 expected_version: int, reason: str | None = None) -> BatchOut:
    batch = load_batch(db, batch_id, lock=True)
    entity = entity_or_404(batch["entity"])
    need(ctx, entity, "write")
    ctx.assert_branch(batch["branch_id"])
    _creator_draft(ctx, batch, expected_version)
    return _submit(db, ctx, meta, entity, batch, reason)


@audited(AuditAction.DATA_BATCH_WITHDRAWN)
def withdraw_batch(db: Session, ctx: AuthContext, meta: ClientMeta, batch_id: int, *,
                   expected_version: int) -> BatchOut:
    batch = load_batch(db, batch_id, lock=True)
    entity = entity_or_404(batch["entity"])
    need(ctx, entity, "write")
    if batch["created_by"] != ctx.user_id:
        raise ForbiddenError()
    if batch["status"] not in ("draft", "submitted"):
        raise ValidationFailed("batch_not_editable", fields=["status"])
    if batch["version"] != expected_version:
        raise ConflictError("conflict_modified")
    db.execute(text("UPDATE core.manual_head SET pending_batch_id = NULL, updated_at = now() "
                    "WHERE pending_batch_id = :b"), {"b": batch_id})
    db.execute(text("UPDATE core.manual_batch SET status = 'withdrawn', version = version + 1 "
                    "WHERE batch_id = :b"), {"b": batch_id})
    out = _stamp(db, batch_id)
    db.commit()
    log_event(meta, AuditAction.DATA_BATCH_WITHDRAWN, user_id=ctx.user_id,
              object_type="manual_batch", object_id=batch_id,
              details={"batch_id": batch_id, "entity": entity.id, "rows": out.rows})
    return out


def get_batch(db: Session, ctx: AuthContext, batch_id: int) -> BatchDetailOut:
    batch = load_batch(db, batch_id)
    entity = entity_or_404(batch["entity"])
    if not (ctx.has(data_perm(entity.section, "write"))
            or ctx.has(data_perm(entity.section, "approve"))):
        raise ForbiddenError()
    return BatchDetailOut(**batch_out(batch).model_dump(), items=changes(db, entity, batch_id))


def list_batches(db: Session, ctx: AuthContext, *, box: Literal["mine", "inbox"],
                 status: str | None = None, page: int = 1) -> Page[BatchOut]:
    action: Literal["write", "approve"] = "approve" if box == "inbox" else "write"
    entity_ids = [e.id for e in ENTITIES.values() if ctx.has(data_perm(e.section, action))]
    if not entity_ids:
        raise ForbiddenError()
    where = "entity = ANY(:ents)"
    params: dict[str, Any] = {"ents": entity_ids, "u": ctx.user_id}
    if box == "mine":
        where += " AND created_by = :u"
    else:  # tasdiqlovchi o'z paketini ko'rmaydi (u baribir tasdiqlay olmaydi)
        where += " AND status = 'submitted' AND created_by <> :u"
    if status:
        where += " AND status = :s"
        params["s"] = status
    total = db.execute(text(f"SELECT count(*) FROM core.manual_batch WHERE {where}"),  # noqa: S608
                       params).scalar_one()
    rows = db.execute(text(
        f"SELECT * FROM core.manual_batch WHERE {where} "  # noqa: S608
        "ORDER BY batch_id DESC LIMIT :n OFFSET :o"),
        {**params, "n": PAGE_SIZE, "o": (max(page, 1) - 1) * PAGE_SIZE}).mappings()
    return Page[BatchOut](items=[batch_out(r) for r in rows], total=total, page=max(page, 1))
