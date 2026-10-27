"""Kundalik Telegram hisoboti (TZ 7 «Второй этап», TZ 8 «Телеграм-бот» — 08:30; S2 spec 9).

Faqat agregatlar (pub view'lar) va KRITIK qoidalar SARLAVHALARI: qoida xabarlarida kontragent
nomi bo'lishi mumkin — ular yuborilmaydi. Shaxsiy ma'lumot, hisob raqami, INN yo'q. Summalar
млрд/трлн сум. Har yuborish auditga yoziladi (tashqi servisga ma'lumot uzatish).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.alerts.engine import evaluate
from app.audit.service import AuditAction, AuditEvent, AuditResult, record
from app.auth.permissions import Section, section_perm
from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.core.logging import get_logger
from app.dwh.dates import TASHKENT
from app.dwh.freshness import freshness
from app.etl.telegram import TelegramConfig, TelegramError, make_client, telegram_config
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_num, fmt_pct
from app.sections.queries import calendar, cash, loans

ALL_SECTIONS = frozenset(section_perm(s) for s in Section)
log = get_logger("ugekazna.daily")


class Sender(Protocol):
    def send(self, chat_id: int, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class Summary:
    text: str
    critical: int
    warning: int


def fmt_bln(mln: float | None) -> str:
    if mln is None:
        return "нет данных"
    if abs(mln) >= 1_000_000:
        return f"{fmt_num(mln / 1_000_000, 2)} трлн сум"
    return f"{fmt_num(mln / 1_000, 1 if abs(mln) >= 1_000 else 2)} млрд сум"


def build_summary(db: Session, *, today: date, now: datetime, base_url: str) -> Summary:
    q = SectionQuery(None, f"m{today.month:02d}", today, None)
    period, sel = q.period(), q.sel()
    totals = cash.cash_totals(db, sel, period)
    block = calendar.calendar(db, sel)
    report = loans.load_report(db, sel, period)
    hits, _ = evaluate(db, q, ALL_SECTIONS)
    state = freshness(db.connection(), now)
    rates = {str(r.currency).strip(): float(r.rate) for r in db.execute(text(
        "SELECT currency, rate FROM pub.fx_rate_latest WHERE currency IN ('USD', 'EUR')")).all()}

    last = "никогда" if state.last_success_at is None else \
        state.last_success_at.astimezone(TASHKENT).strftime("%d.%m.%Y %H:%M")
    lines = [f"UGEKAZNA — сводка на {today:%d.%m.%Y}",
             f"Данные загружены: {last}" + (" — ДАННЫЕ УСТАРЕЛИ" if state.stale else ""),
             "", "Денежные средства",
             f"• Остаток на счетах: {fmt_bln(totals.closing)}",
             f"• С начала месяца: поступления {fmt_bln(totals.inflow)}, "
             f"расходование {fmt_bln(totals.outflow)}"]
    if block.total > 0:
        cover = "" if block.coverage is None else \
            f", остаток покрывает в {fmt_num(block.coverage, 1)} раза"
        lines.append(f"• Платежи на 14 дней: {fmt_bln(block.total)}{cover}")
    else:
        lines.append("• Платежи на 14 дней: нет данных")
    lines += ["", "Кредиты"]
    if report.has_loans:
        share = "нет данных" if report.fx_share is None else fmt_pct(report.fx_share)
        lines.append(f"• Портфель: {fmt_bln(report.portfolio)}, доля валютных {share}")
        nxt = report.next_payment
        if nxt is not None:
            lines.append(f"• Ближайший платёж: {nxt.day:%d.%m.%Y} — {fmt_bln(nxt.total)}")
    else:
        lines.append("• Кредитов нет")
    if rates:
        lines += ["", "Курсы ЦБ: " + ", ".join(
            f"{c} {fmt_num(rates[c], 2)}" for c in ("USD", "EUR") if c in rates)]
    critical = [h for h in hits if h.level == "critical"]
    warning = len(hits) - len(critical)
    lines += ["", f"Требует внимания: критично {len(critical)}, внимание {warning}"]
    lines += [f"• {h.title}" for h in critical]
    lines.append(f"Подробнее: {base_url.rstrip('/')}/#obzor/vnimanie")
    return Summary("\n".join(lines), len(critical), warning)


def send_daily_summary(*, client: Sender | None = None, now: datetime | None = None,
                       loader: Callable[[], TelegramConfig | None] = telegram_config) -> int:
    """Konfiguratsiya (token + chat'lar) panelda — har chaqiruvda o'qiladi; sozlanmagan - 0."""
    cfg = loader()
    if cfg is None:
        log.info("telegram_summary_skipped", reason="not_configured")
        return 0
    sender: Sender = client or make_client(cfg)
    moment = now or datetime.now(UTC)
    with new_session() as s:
        apply_rls(s, None)
        summary = build_summary(s, today=moment.astimezone(TASHKENT).date(), now=moment,
                                base_url=get_settings().base_url)
    sent = 0
    for chat in cfg.chats:
        try:
            sender.send(chat, summary.text)
            sent += 1
        except TelegramError as exc:
            log.error("telegram_summary_failed", error=str(exc))
    result: AuditResult = "ok" if sent == len(cfg.chats) else "fail"
    record(AuditEvent(action=AuditAction.TELEGRAM_SUMMARY_SENT, result=result,
                      object_type="telegram",
                      details={"chats": len(cfg.chats), "sent": sent, "critical": summary.critical,
                               "chars": len(summary.text)}))
    return sent
