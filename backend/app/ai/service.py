"""AI-анализ oqimi (TZ 7, S5 spec 4.1): tayyorlash (sinxron, threadpool) va SSE (asinxron).

Tayyorlash tartibi: funksiya yoqilganmi → savol → kontekst (foydalanuvchi RLS tranzaksiyasida)
→ tranzaksiya yopiladi (ulanish oqim davomida band qilinmaydi) → limit + jurnal yozuvi → audit.
Oqim: `start` → `delta`… → `done` | `error`; 60 s — umumiy muddat; mijoz uzilsa (generator
yopiladi) provayder oqimi yopiladi va jurnalga `cancelled` yoziladi. Prompt va javob matni log'ga
yozilmaydi.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.ai import journal
from app.ai.context import assemble_context, check_question
from app.ai.prompt import SYSTEM_PROMPT, build_prompt
from app.ai.provider import AI_TIMEOUT_S, AiProvider, AiProviderError
from app.ai.schemas import AiAnalyzeIn
from app.audit.service import AuditAction, log_event
from app.auth.context import AuthContext
from app.core.errors import AiDisabledError, AiLimitError
from app.core.request_meta import ClientMeta
from app.dwh.reference import current_setting

ERROR_TEXT = {
    "ai_timeout": "Время ожидания ответа истекло (60 секунд). Попробуйте сузить вопрос.",
    "ai_unavailable": "Сервис анализа временно недоступен. Повторите позже.",
    "ai_busy": "Сервис анализа перегружен. Повторите через минуту.",
    "ai_refused": "Модель отказалась отвечать на этот запрос. Переформулируйте вопрос.",
    "ai_misconfigured": "AI-анализ настроен неверно — обратитесь к администратору.",
    "ai_failed": "Не удалось получить ответ. Попробуйте ещё раз.",
}
_STATUS_BY_CODE = {"ai_timeout": "timeout", "ai_refused": "refused"}


@dataclass(frozen=True, slots=True)
class Job:
    request_id: int
    system: str
    prompt: str
    provider: AiProvider


def feature_state(conn: Connection,
                  provider: AiProvider | None) -> Literal["disabled", "not_configured"] | None:
    if current_setting(conn, "ai.enabled") is not True:
        return "disabled"
    if provider is None:
        return "not_configured"
    return None


def prepare(db: Session, ctx: AuthContext, body: AiAnalyzeIn, provider: AiProvider | None,
            meta: ClientMeta, *, today: date, now: datetime) -> Job:
    if provider is None or feature_state(db.connection(), provider) is not None:
        raise AiDisabledError()
    check_question(body.question)
    base = {"section": body.section, "page": body.page,
            "filters": {"br": body.br, "per": body.per}}
    try:
        journal.precheck(ctx.user_id, now)  # M2: limit oshgan so'rov kontekst qurmaydi
    except AiLimitError as exc:
        log_event(meta, AuditAction.AI_REQUEST, user_id=ctx.user_id, result="denied",
                  object_type="ai_request",
                  details={**base, "reason": "limit", "scope": exc.params["scope"]})
        raise
    context = assemble_context(db, ctx, body, today=today, now=now)
    db.commit()  # RLS tranzaksiyasi tugaydi — ulanish oqim davomida ushlab turilmaydi
    filters: dict[str, Any] = {"br": body.br, "per": body.per}
    if body.section == "finmodel":
        filters["scen"] = body.scen
    base = {"section": body.section, "page": body.page, "filters": filters}
    warm = getattr(provider, "warm", None)
    if warm is not None:
        try:
            warm()  # kalit/mijoz threadpool'da tayyorlanadi
        except AiProviderError:
            raise AiDisabledError() from None  # kalit yo'qolgan — «не настроен»
    try:
        request_id = journal.reserve(journal.NewRequest(
            ctx.user_id, body.section, body.page, filters, body.preset, body.question,
            context.chars, provider.name, provider.model), now=now)
    except AiLimitError as exc:
        log_event(meta, AuditAction.AI_REQUEST, user_id=ctx.user_id, result="denied",
                  object_type="ai_request",
                  details={**base, "reason": "limit", "scope": exc.params["scope"]})
        raise
    log_event(meta, AuditAction.AI_REQUEST, user_id=ctx.user_id, object_type="ai_request",
              object_id=request_id,
              details={**base, "preset": body.preset, "context_chars": context.chars,
                       "model": provider.model})
    prompt = build_prompt(context.text, preset=body.preset, question=body.question)
    return Job(request_id, SYSTEM_PROMPT, prompt, provider)


def sse(event: str, data: dict[str, Any]) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode()


async def stream_events(job: Job, *, timeout: float = AI_TIMEOUT_S,
                        clock: Callable[[], float] = time.monotonic) -> AsyncIterator[bytes]:
    started = clock()
    deadline = started + timeout
    chars = 0
    status, code = "cancelled", None  # yopilish (mijoz uzildi) — standart natija
    chunks = job.provider.stream(job.system, job.prompt)
    try:
        yield sse("start", {"request_id": job.request_id})
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                raise TimeoutError
            try:
                part = await asyncio.wait_for(anext(chunks), remaining)
            except StopAsyncIteration:
                break
            chars += len(part)
            yield sse("delta", {"text": part})
        status = "ok"
        yield sse("done", {"length": chars})
    except TimeoutError:
        status, code = "timeout", "ai_timeout"
        yield sse("error", {"code": code, "message": ERROR_TEXT[code]})
    except AiProviderError as exc:
        status, code = _STATUS_BY_CODE.get(exc.code, "error"), exc.code
        yield sse("error", {"code": code, "message": ERROR_TEXT[code]})
    finally:
        with contextlib.suppress(Exception):
            await chunks.aclose()  # type: ignore[attr-defined]
        duration = int((clock() - started) * 1000)
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.shield(asyncio.to_thread(
                journal.finish, job.request_id, status=status, error_code=code,
                answer_chars=chars, duration_ms=duration))
