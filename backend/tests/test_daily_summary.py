import re
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text

from app import cli, worker
from app.core.config import get_settings
from app.core.db import apply_rls, get_engine, new_session
from app.etl.telegram import TelegramConfig, TelegramError
from app.reports.daily import build_summary, fmt_bln, send_daily_summary
from tests.etl_helpers import RecordingNotifier

TOKEN = "123456789:" + "A" * 35
NOW = datetime(2026, 9, 24, 3, 30, tzinfo=UTC)  # 08:30 Toshkent


class FakeClient:
    def __init__(self, fail_for: frozenset[int] = frozenset()) -> None:
        self.sent: list[tuple[int, str]] = []
        self.fail_for = fail_for

    def send(self, chat_id: int, text: str) -> None:
        if chat_id in self.fail_for:
            raise TelegramError("Telegram: HTTP 403")
        self.sent.append((chat_id, text))


def _cfg(chats: tuple[int, ...] = (1, 2), scope: str = "org_totals") -> object:
    return lambda: TelegramConfig(TOKEN, list(chats), False, scope)


def test_fmt_bln() -> None:
    assert fmt_bln(1234.5) == "1,2 млрд сум"
    assert fmt_bln(12) == "0,01 млрд сум"
    assert fmt_bln(2_500_000) == "2,50 трлн сум"
    assert fmt_bln(None) == "нет данных"


def test_summary_text_has_aggregates_and_no_personal_data(published_synthetic: int) -> None:
    with new_session() as s:
        apply_rls(s, None)
        summary = build_summary(s, today=date(2026, 9, 24), now=NOW,
                                base_url="https://ugekazna.test")
    body = summary.text
    assert body.startswith("UGEKAZNA — сводка на 24.09.2026")
    for needle in ("Денежные средства", "Остаток на счетах:", "С начала месяца:",
                   "Платежи на 14 дней:", "Кредиты", "Портфель:", "Требует внимания: критично",
                   "https://ugekazna.test/#obzor/vnimanie"):
        assert needle in body, needle
    assert "сум" in body and "млн" not in body
    assert not re.search(r"\d{10,}", body)  # hisob raqamlari / INN yo'q
    assert "ООО" not in body and "«" not in body  # kontragent nomlari yo'q
    tail = body.split("Требует внимания:", 1)[1]
    # A-S2.R1: faqat sonlar, qoida sarlavhalari/xabarlari yuborilmaydi
    assert not any(line.startswith("• ") for line in tail.splitlines()[1:])


def test_send_daily_summary_audits(published_synthetic: int) -> None:
    fake = FakeClient()
    assert send_daily_summary(client=fake, now=NOW, loader=_cfg()) == 2
    assert [chat for chat, _ in fake.sent] == [1, 2]
    with get_engine("migrator").connect() as conn:
        row = conn.execute(text(
            "SELECT result, details FROM core.audit_log WHERE action = 'notify.telegram.summary' "
            "ORDER BY id DESC LIMIT 1")).one()
    assert row.result == "ok" and row.details["chats"] == 2 and row.details["sent"] == 2
    partial = FakeClient(frozenset({2}))
    assert send_daily_summary(client=partial, now=NOW, loader=_cfg()) == 1
    with get_engine("migrator").connect() as conn:
        result = conn.execute(text(
            "SELECT result FROM core.audit_log WHERE action = 'notify.telegram.summary' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert result == "fail"


def test_skipped_without_config_and_job_registered(capsys: pytest.CaptureFixture[str]) -> None:
    assert send_daily_summary(client=FakeClient(), now=NOW) == 0  # test muhitida token yo'q
    jobs = {j.id for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert "telegram_summary" in jobs  # shartsiz; sozlanmagan bo'lsa tanasi o'tkazib yuboradi
    assert cli.main(["telegram-test"]) == 2
    assert "Telegram" in capsys.readouterr().out


def test_scope_off_sends_nothing() -> None:
    fake = FakeClient()
    assert send_daily_summary(client=fake, now=NOW, loader=_cfg(scope="off")) == 0
    assert fake.sent == []
