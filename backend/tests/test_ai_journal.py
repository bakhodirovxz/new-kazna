from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.ai.admin import set_ai_enabled
from app.ai.journal import (
    NewRequest,
    finish,
    precheck,
    purge,
    reserve,
    retry_after,
    used_last_hour,
)
from app.cli import main as cli_main
from app.core.db import get_engine
from app.core.errors import AiLimitError
from app.dwh.reference import current_setting
from app.etl.db import etl_transaction
from tests.helpers import clear_setting, create_user, put_setting


@pytest.fixture(autouse=True)
def _clean_journal() -> Iterator[None]:
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM core.ai_requests"))
    yield
    for key in ("ai.user_per_hour", "ai.org_per_day", "ai.enabled"):
        clear_setting(key)


def _req(user_id: int) -> NewRequest:
    return NewRequest(user_id=user_id, section="obzor", page="svod",
                      filters={"br": None, "per": "ytd"}, preset="risks", question=None,
                      context_chars=1200, provider="fake", model="fake-model")


def _insert(user_id: int, created: datetime, status: str = "ok") -> int:
    with get_engine("app").begin() as conn:
        return int(conn.execute(text(
            "INSERT INTO core.ai_requests (created_at, user_id, section, page, status, "
            "context_chars, provider, model) VALUES (:c, :u, 'obzor', 'svod', :s, 10, 'fake', "
            "'fake-model') RETURNING id"), {"c": created, "u": user_id, "s": status}).scalar_one())


def _row(request_id: int) -> dict[str, object]:
    with get_engine("app").connect() as conn:
        return dict(conn.execute(text("SELECT * FROM core.ai_requests WHERE id = :i"),
                                 {"i": request_id}).mappings().one())


def test_retry_after_math() -> None:
    now = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    times = [now - timedelta(minutes=m) for m in (50, 40, 10)]
    assert retry_after(times, 3, timedelta(hours=1), now) == 600
    assert retry_after(times, 4, timedelta(hours=1), now) is None
    assert retry_after(times, 2, timedelta(hours=1), now) == 1200


def test_reserve_inserts_running_row() -> None:
    user = create_user("rukovodstvo")
    request_id = reserve(_req(user.id), now=datetime.now(UTC))
    row = _row(request_id)
    assert (row["status"], row["section"], row["preset"], row["context_chars"]) == (
        "running", "obzor", "risks", 1200)
    assert row["filters"] == {"br": None, "per": "ytd"} and row["question"] is None
    with get_engine("app").connect() as conn:
        assert used_last_hour(conn, user.id, datetime.now(UTC)) == 1


def test_user_limit_and_retry_after() -> None:
    put_setting("ai.user_per_hour", 3)
    user, other = create_user("rukovodstvo"), create_user("rukovodstvo")
    now = datetime.now(UTC)
    for minutes in (50, 40, 10):
        _insert(user.id, now - timedelta(minutes=minutes))
    _insert(user.id, now - timedelta(minutes=70))  # oynadan tashqari
    with pytest.raises(AiLimitError) as exc:
        reserve(_req(user.id), now=now)
    assert exc.value.params["scope"] == "user"
    assert 599 <= exc.value.params["retry_after"] <= 600
    assert reserve(_req(other.id), now=now) > 0


def test_org_limit() -> None:
    put_setting("ai.org_per_day", 2)
    first, second, third = (create_user("rukovodstvo") for _ in range(3))
    now = datetime.now(UTC)
    _insert(first.id, now - timedelta(hours=23))
    _insert(second.id, now - timedelta(hours=1))
    _insert(first.id, now - timedelta(hours=25))  # oynadan tashqari
    with pytest.raises(AiLimitError) as exc:
        reserve(_req(third.id), now=now)
    assert exc.value.params["scope"] == "org"
    assert 3599 <= exc.value.params["retry_after"] <= 3600


def test_finish_updates_running_row_once() -> None:
    user = create_user("rukovodstvo")
    request_id = reserve(_req(user.id), now=datetime.now(UTC))
    finish(request_id, status="ok", error_code=None, answer_chars=512, duration_ms=1500)
    finish(request_id, status="cancelled", error_code=None, answer_chars=0, duration_ms=9)
    row = _row(request_id)
    assert (row["status"], row["answer_chars"], row["duration_ms"]) == ("ok", 512, 1500)
    assert row["finished_at"] is not None


def test_purge_retention_and_stale_rows() -> None:
    user = create_user("rukovodstvo")
    now = datetime.now(UTC)
    old = _insert(user.id, now - timedelta(days=91))
    kept = _insert(user.id, now - timedelta(days=89))
    stale = _insert(user.id, now - timedelta(minutes=11), status="running")
    fresh = _insert(user.id, now - timedelta(minutes=5), status="running")
    assert purge(now) == (1, 1)
    with get_engine("app").connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM core.ai_requests")).scalars())
        audit = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'ai.journal.purged' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert old not in ids and {kept, stale, fresh} <= ids
    assert (_row(stale)["status"], _row(stale)["error_code"]) == ("error", "stale")
    assert _row(fresh)["status"] == "running"
    assert audit["deleted"] == 1 and audit["stale"] == 1 and audit["retention_days"] == 90
    assert purge(now) == (0, 0)


def test_ai_enable_cli_is_versioned_and_audited() -> None:
    assert cli_main(["ai-enable", "on", "--reason", "Письмо ИБ №12 от 01.10.2026"]) == 0
    with get_engine("app").connect() as conn:
        assert current_setting(conn, "ai.enabled") is True
        details = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.setting.updated' "
            "AND object_id = 'ai.enabled' ORDER BY id DESC LIMIT 1")).scalar_one()
    assert details["before"] is False and details["after"] is True
    assert details["via"] == "cli" and details["reason"].startswith("Письмо ИБ")
    assert set_ai_enabled(True, "повтор повтор") is False  # o'zgarish yo'q — yozuv ham yo'q
    assert set_ai_enabled(False, "тест завершён") is True
    with get_engine("app").connect() as conn:
        assert current_setting(conn, "ai.enabled") is False


def test_ai_enable_cli_requires_reason() -> None:
    with pytest.raises(SystemExit):
        cli_main(["ai-enable", "on", "--reason", "x"])


def test_precheck_blocks_before_reserve() -> None:
    put_setting("ai.user_per_hour", 1)
    user = create_user("rukovodstvo")
    now = datetime.now(UTC)
    precheck(user.id, now)
    _insert(user.id, now - timedelta(minutes=5))
    with pytest.raises(AiLimitError) as exc:
        precheck(user.id, now)
    assert exc.value.params["scope"] == "user"
