"""AI-анализ HTTP API (TZ 7): holat, oqimli tahlil, jurnal (audit:read)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.admin.schemas import Page
from app.ai import journal
from app.ai.provider import AiProvider, get_ai_provider
from app.ai.schemas import AiAnalyzeIn, AiRequestOut, AiStatusOut
from app.ai.service import feature_state, prepare, stream_events
from app.auth.context import AuthContext, Ctx, require_perm
from app.auth.permissions import Perm
from app.core.db import DB
from app.core.request_meta import Meta
from app.sections.deps import Today

router = APIRouter(prefix="/ai", tags=["ai"])
journal_router = APIRouter(prefix="/audit", tags=["audit"])
Provider = Annotated[AiProvider | None, Depends(get_ai_provider)]
Auditor = Annotated[AuthContext, Depends(require_perm(Perm.AUDIT_READ))]


@router.get("/status", response_model=AiStatusOut)
def status(ctx: Ctx, db: DB, provider: Provider) -> AiStatusOut:
    conn = db.connection()
    reason = feature_state(conn, provider)
    per_user, per_org = journal.limits(conn)
    used = journal.used_last_hour(conn, ctx.user_id, datetime.now(UTC)) if reason is None else 0
    return AiStatusOut(enabled=reason is None, reason=reason, user_per_hour=per_user,
                       org_per_day=per_org, used_last_hour=used)


@router.post("/analyze", response_class=StreamingResponse,
             responses={200: {"content": {"text/event-stream": {}}}})
async def analyze(body: AiAnalyzeIn, ctx: Ctx, db: DB, provider: Provider, meta: Meta,
                  today: Today) -> StreamingResponse:
    job = await run_in_threadpool(prepare, db, ctx, body, provider, meta, today=today,
                                  now=datetime.now(UTC))
    return StreamingResponse(stream_events(job), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@journal_router.get("/ai-requests", response_model=Page[AiRequestOut])
def ai_requests(_: Auditor, db: DB, page: Annotated[int, Query(ge=1)] = 1,
                page_size: Annotated[int, Query(ge=1, le=500)] = 50) -> Page[AiRequestOut]:
    total = int(db.execute(text("SELECT count(*) FROM core.ai_requests")).scalar_one())
    rows = db.execute(text(
        "SELECT r.id, r.created_at, r.finished_at, u.username, r.section, r.page, r.filters, "
        "r.preset, r.question, r.status, r.error_code, r.context_chars, r.answer_chars, "
        "r.model, r.duration_ms FROM core.ai_requests r JOIN core.users u ON u.id = r.user_id "
        "ORDER BY r.id DESC LIMIT :l OFFSET :o"),
        {"l": page_size, "o": (page - 1) * page_size}).mappings().all()
    items = [AiRequestOut(**dict(r)) for r in rows]
    return Page[AiRequestOut](items=items, total=total, page=page, page_size=page_size)
