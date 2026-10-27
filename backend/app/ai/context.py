"""AI konteksti (TZ 7 «Состав контекста», S5 spec 4.2) — faqat agregatlar, ≤ 14 000 belgi.

Manba — foydalanuvchi ochgan sahifaning mavjud quruvchisi (`app.sections.<bo'lim>.build_<sahifa>`,
RLS va filial doirasi bilan — xuddi sahifaning o'zi kabi), undan OQ RO'YXAT bo'yicha: raqamlar,
sanalar va ruxsat etilgan matn kalitlari. Kodlar, raqamlar, `*_id` (month_id dan tashqari),
kontragent/yetkazib beruvchi nomlari va sezgir kalitlar tashlanadi. Qoidalardan faqat daraja,
sarlavha, bo'lim va qiymat (xabar matnida kontragent nomi bo'lishi mumkin). Yakuniy matn
skanerdan o'tadi; topilsa — so'rov rad etiladi (fail-closed).
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.schemas import AiAnalyzeIn
from app.ai.sensitive import SENSITIVE_KEY_RE, find_sensitive_text
from app.auth.context import AuthContext
from app.auth.permissions import SECTION_TITLES, Section, section_perm
from app.core.errors import ForbiddenError, ValidationFailed
from app.core.logging import get_logger
from app.dwh.dates import TASHKENT
from app.dwh.freshness import freshness
from app.meta.menu import MENU
from app.sections.deps import SectionQuery

MAX_CONTEXT_CHARS = 14_000
LIST_CAPS = (12, 6, 3)
TRUNCATED = "…(данные сокращены)"
UNITS = ("суммы — млн сум (если не указано иное); доли — от 0 до 1; мощность — МВт; "
         "выработка — млн кВт·ч; тариф и себестоимость — сум за кВт·ч")
TEXT_KEYS = frozenset({
    "name", "short_name", "title", "label", "status", "method", "method_title", "category",
    "currency", "creditor", "project", "kind", "activity", "direction", "level", "work_type",
    "source_name", "scenario", "section", "page", "item_name", "branch_name", "subject", "unit",
    "stage_name", "verdict",
})
KEEP_ID_KEYS = frozenset({"month_id"})
DROP_KEYS = frozenset({"message", "code", "comment", "description", "lot_no", "number",
                       "object_code", "loan_code", "program_code", "src_id", "doc_id",
                       "request_id", "checked"})
DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?(T[\d:.]+(Z|[+-]\d{2}:\d{2})?)?$")
# Faqat qurilgan bo'limlar import qilinadi; qolganlari (S2–S4, finmodel) qo'shilganda ishlaydi.
SECTION_MODULES: dict[Section, str] = {
    Section.OBZOR: "app.sections.obzor",
    Section.KAZNA: "app.sections.kazna",
    Section.KREDITY: "app.sections.kredity",
    Section.PROIZVODSTVO: "app.sections.proizvodstvo",
    Section.SKLAD: "app.sections.sklad",
    Section.ZAKUPKI: "app.sections.zakupki",
    Section.INVESTICII: "app.sections.investicii",
    Section.KADRY: "app.sections.kadry",
}
FLOW_PAGES = {"postup": "in", "rasxod": "out"}  # obzor: build_flow(db, q, direction)
YOY_BLOCK = "денежные средства (с прошлым годом)"
log = get_logger("ugekazna.ai")


class _Skip:
    """Tashlanadigan qiymat belgisi."""


_SKIP = _Skip()


@dataclass(frozen=True, slots=True)
class AiContext:
    text: str
    chars: int
    section_title: str
    page_title: str


def _allowed_key(key: str) -> bool:
    if key in DROP_KEYS or SENSITIVE_KEY_RE.search(key):
        return False
    return not (key.endswith("_id") and key not in KEEP_ID_KEYS)


def _walk(value: Any, cap: int, key: str) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k, v in value.items():
            name = str(k)
            if not _allowed_key(name):
                continue
            item = _walk(v, cap, name)
            if item is not _SKIP:
                out[name] = item
        return out
    if isinstance(value, (list, tuple)):
        items = [x for x in (_walk(v, cap, key) for v in value[:cap]) if x is not _SKIP]
        if len(value) > cap:
            items.append(f"… ещё {len(value) - cap}")
        return items
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, str):
        return value[:120] if key in TEXT_KEYS or DATE_RE.match(value) else _SKIP
    return _SKIP


def digest(value: Any, cap: int = LIST_CAPS[0], key: str = "") -> Any:
    """Oq ro'yxat bo'yicha agregat qoldiq (dict/list/raqam/sana/ruxsat etilgan matn)."""
    result = _walk(value, cap, key)
    return None if result is _SKIP else result


def _dump(doc: Mapping[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def fit(header: Mapping[str, Any], blocks: Mapping[str, Any]) -> str:
    """Ro'yxatlarni 12 → 6 → 3 gacha qisqartirib 14 000 belgiga sig'diradi; oxirida — kesish."""
    doc_text = ""
    for cap in LIST_CAPS:
        doc = {**header, **{name: digest(value, cap) for name, value in blocks.items()}}
        doc_text = _dump(doc)
        if len(doc_text) <= MAX_CONTEXT_CHARS:
            return doc_text
    return doc_text[: MAX_CONTEXT_CHARS - len(TRUNCATED)] + TRUNCATED


def page_title(section: Section, page: str) -> str:
    for item in MENU:
        if item.section == section:
            for p in item.pages:
                if p.id == page:
                    return p.title
    raise ValidationFailed("validation_failed", fields=["page"])


def check_question(question: str | None) -> None:
    if question and find_sensitive_text(question):
        raise ValidationFailed("ai_question_sensitive")


def _page_payload(db: Session, section: Section, page: str, q: SectionQuery) -> Any:
    module_name = SECTION_MODULES.get(section)
    try:
        if module_name is None:
            raise ModuleNotFoundError(section.value)
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        raise ValidationFailed("validation_failed", fields=["section"]) from None
    if section == Section.OBZOR and page in FLOW_PAGES:
        return module.build_flow(db, q, FLOW_PAGES[page])
    builder: Callable[..., Any] | None = getattr(module, f"build_{page}", None)
    if builder is None or len(inspect.signature(builder).parameters) != 2:
        builder = module.build_svod  # masalan, «Требует внимания» — qoidalar alohida blokda
    return builder(db, q)


def _data_time(db: Session, now: datetime) -> str:
    state = freshness(db.connection(), now)
    if state.last_success_at is None:
        return "успешных загрузок ещё не было"
    return state.last_success_at.astimezone(TASHKENT).strftime("%d.%m.%Y %H:%M")


def _branch_name(db: Session, br: int | None) -> str:
    if br is None:
        return "все филиалы"
    name = db.execute(text("SELECT name FROM pub.branches WHERE branch_id = :b"),
                      {"b": br}).scalar_one_or_none()
    return str(name) if name else f"филиал {br}"


def assemble_context(db: Session, ctx: AuthContext, req: AiAnalyzeIn, *, today: date,
                     now: datetime) -> AiContext:
    from app.alerts.engine import build_alerts
    from app.sections import obzor

    try:
        section = Section(req.section)
    except ValueError:
        raise ValidationFailed("validation_failed", fields=["section"]) from None
    if not ctx.has(section_perm(section)):
        raise ForbiddenError()
    title = page_title(section, req.page)
    ctx.assert_branch(req.br)
    q = SectionQuery(req.br, req.per, today, ctx.branch_ids)
    header = {
        "раздел": SECTION_TITLES[section], "страница": title,
        "филиал": _branch_name(db, req.br), "период": q.period().label,
        "дата данных": _data_time(db, now), "единицы": UNITS,
    }
    blocks: dict[str, Any] = {"показатели страницы": _page_payload(db, section, req.page, q)}
    if section != Section.OBZOR and ctx.has(section_perm(Section.OBZOR)):
        blocks[YOY_BLOCK] = obzor.build_svod(db, q).kpis
    alerts = build_alerts(db, q, ctx.permissions)
    blocks["сработавшие правила"] = [
        {"level": a.level, "title": a.title, "section": a.section, "value": a.value}
        for a in alerts.items]
    context_text = fit(header, blocks)
    problems = find_sensitive_text(context_text)
    if problems:
        log.warning("ai_context_rejected", section=section.value, page=req.page, kinds=problems)
        raise ValidationFailed("ai_context_rejected")
    return AiContext(context_text, len(context_text), SECTION_TITLES[section], title)
