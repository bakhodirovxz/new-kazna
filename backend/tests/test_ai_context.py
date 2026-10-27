import importlib.util
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.context import (
    MAX_CONTEXT_CHARS,
    SECTION_MODULES,
    TRUNCATED,
    YOY_BLOCK,
    assemble_context,
    check_question,
    digest,
    fit,
)
from app.ai.prompt import PRESETS, SYSTEM_PROMPT, build_prompt
from app.ai.schemas import AiAnalyzeIn
from app.ai.sensitive import SENSITIVE_KEY_RE, find_sensitive_keys, find_sensitive_text
from app.auth.context import AuthContext, build_context
from app.auth.models import User
from app.core.db import apply_rls, new_session
from app.core.errors import ForbiddenError, ScopeViolationError, ValidationFailed
from app.etl.db import etl_transaction
from app.meta.menu import MENU
from tests.etl_helpers import TEST_AS_OF
from tests.helpers import SeedUser, create_user

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


def _session_for(user: SeedUser) -> Iterator[tuple[Session, AuthContext]]:
    with new_session() as db:
        row = db.get(User, user.id)
        assert row is not None
        auth = build_context(db, row, uuid.uuid4(), NOW)
        apply_rls(db, auth.branch_ids)
        yield db, auth


@pytest.fixture
def admin_ctx() -> Iterator[tuple[Session, AuthContext]]:
    yield from _session_for(create_user("rukovodstvo"))


def _req(section: str, page: str, **extra: Any) -> AiAnalyzeIn:
    return AiAnalyzeIn(section=section, page=page, per="ytd", **extra)


def test_digest_keeps_only_whitelisted_aggregates() -> None:
    payload = {
        "inn": "301234567", "cp_name": "ООО «Ромашка»", "supplier": "ИП Иванов",
        "account": "20208000900100000001", "full_name": "Иванов И. И.",
        "responsible_person": "Петров", "number": "№ 1/2025", "lot_no": "L-1",
        "branch_id": 3, "month_id": 202608, "name": "Чарвакская ГЭС",
        "amount": 1234.5678, "note": "ИНН 301234567 в тексте", "date": "2026-08-31",
        "rows": [{"creditor": "АБР", "passport_no": "AA1234567", "value": 1.0}] * 20,
        "message": "Договор с ООО «Ромашка» просрочен",
    }
    out = digest(payload)
    assert set(out) == {"month_id", "name", "amount", "date", "rows"}
    assert out["amount"] == 1234.57
    assert len(out["rows"]) == 13 and out["rows"][-1] == "… ещё 8"
    assert out["rows"][0] == {"creditor": "АБР", "value": 1.0}
    assert find_sensitive_keys(out) == []
    assert find_sensitive_text(json.dumps(out, ensure_ascii=False)) == []


def test_fit_caps_context_size() -> None:
    header = {"раздел": "Обзор"}
    blocks = {"показатели": {"items": [{"name": f"Статья {i}", "amount": i * 1.5}
                                        for i in range(5000)]}}
    small = fit(header, {"показатели": {"items": [{"name": "A", "amount": 1.0}]}})
    assert json.loads(small)["показатели"]["items"] == [{"name": "A", "amount": 1.0}]
    big = fit(header, blocks)
    assert len(big) <= MAX_CONTEXT_CHARS
    huge = fit(header, {f"b{i}": {"name": "Ж" * 110} for i in range(400)})
    assert len(huge) <= MAX_CONTEXT_CHARS and huge.endswith(TRUNCATED)


def test_sensitive_patterns() -> None:
    assert find_sensitive_text("ИНН 301234567") == ["inn"]
    assert find_sensitive_text("счёт 20208000900100000001") == ["account"]
    assert find_sensitive_text("паспорт AA1234567") == ["passport"]
    assert find_sensitive_text("ПИНФЛ 30101199912345") == ["pinfl"]
    assert find_sensitive_text("выручка 1234567.5 млн, 202609, 20260924, 2026-09-24") == []
    for key in ("inn", "cp_inn", "account_enc", "full_name", "responsible_person", "pinfl",
                "supplier", "counterparty_name", "phone", "inn_bidx"):
        assert SENSITIVE_KEY_RE.search(key), key
    for key in ("opening", "month_id", "name", "creditor", "revenue", "dinner_count"):
        assert not SENSITIVE_KEY_RE.search(key), key


def test_question_check_and_schema() -> None:
    check_question("Почему выросли расходы на ремонт?")
    check_question(None)
    for bad in ("Проверь ИНН 301234567", "Счёт 20208000900100000001 чей?"):
        with pytest.raises(ValidationFailed) as exc:
            check_question(bad)
        assert exc.value.code == "ai_question_sensitive"
    with pytest.raises(ValueError):
        AiAnalyzeIn(section="obzor", page="svod", preset="risks", question="Что?")
    with pytest.raises(ValueError):
        AiAnalyzeIn(section="obzor", page="svod", question="x" * 501)
    with pytest.raises(ValueError):
        AiAnalyzeIn(section="obzor", page="svod", question="строка\x00")
    with pytest.raises(ValueError):
        AiAnalyzeIn(section="obzor", page="svod", extra_field=1)  # type: ignore[call-arg]


def test_prompt_shape() -> None:
    assert "## Что важно заметить" in SYSTEM_PROMPT and "млрд" in SYSTEM_PROMPT
    assert "только" in SYSTEM_PROMPT
    prompt = build_prompt('{"a":1}', preset="risks", question=None)
    assert prompt.startswith('<данные>\n{"a":1}\n</данные>')
    assert PRESETS["risks"] in prompt
    custom = build_prompt("{}", preset=None, question="Почему упала выручка?")
    assert "<вопрос>\nПочему упала выручка?\n</вопрос>" in custom


def _built_pages() -> list[tuple[str, str]]:
    """Faqat hozirgi shoxda qurilgan bo'limlar (S2–S4 / finmodel keyin qo'shiladi)."""
    return [(m.section.value, p.id) for m in MENU
            if m.section in SECTION_MODULES
            and importlib.util.find_spec(SECTION_MODULES[m.section]) is not None
            for p in m.pages]


@pytest.mark.usefixtures("published_synthetic")
def test_every_page_context_is_clean(admin_ctx: tuple[Session, AuthContext]) -> None:
    db, auth = admin_ctx
    pages = _built_pages()
    assert ("obzor", "svod") in pages and ("kazna", "dogovory") in pages
    for section, page in pages:
        ctx = assemble_context(db, auth, _req(section, page), today=TEST_AS_OF, now=NOW)
        where = f"{section}/{page}"
        assert 0 < ctx.chars == len(ctx.text) <= MAX_CONTEXT_CHARS, where
        assert find_sensitive_text(ctx.text) == [], where
        if not ctx.text.endswith(TRUNCATED):
            assert find_sensitive_keys(json.loads(ctx.text)) == [], where


@pytest.mark.usefixtures("published_synthetic")
def test_kazna_dogovory_context_has_no_counterparty(
        admin_ctx: tuple[Session, AuthContext]) -> None:
    db, auth = admin_ctx
    ctx = assemble_context(db, auth, _req("kazna", "dogovory"), today=TEST_AS_OF, now=NOW)
    with etl_transaction() as conn:
        names = [str(n) for n in conn.execute(text(
            "SELECT name FROM dwh.dim_counterparty WHERE length(name) > 5")).scalars()]
    assert names, "sintetik kontragentlar yuklanmagan"
    assert not [n for n in names if n in ctx.text]
    assert "№" not in ctx.text


@pytest.mark.usefixtures("published_synthetic")
def test_header_alerts_and_yoy_block(admin_ctx: tuple[Session, AuthContext]) -> None:
    db, auth = admin_ctx
    ctx = assemble_context(db, auth, _req("kazna", "svod"), today=TEST_AS_OF, now=NOW)
    doc = json.loads(ctx.text)
    assert (doc["раздел"], doc["страница"], doc["филиал"]) == ("Казначейство", "Сводка",
                                                              "все филиалы")
    assert "единицы" in doc and "дата данных" in doc
    assert YOY_BLOCK in doc
    assert all(set(a) <= {"level", "title", "section", "value"}
               for a in doc["сработавшие правила"])
    assert ctx.page_title == "Сводка"


@pytest.mark.usefixtures("published_synthetic")
def test_permissions_scope_and_unknown_page() -> None:
    user = create_user("economist_filiala", branch_ids=(3,))
    for db, auth in _session_for(user):
        ctx = assemble_context(db, auth, _req("kazna", "svod", br=3), today=TEST_AS_OF, now=NOW)
        assert ctx.chars > 0
        with pytest.raises(ForbiddenError):
            assemble_context(db, auth, _req("kredity", "svod"), today=TEST_AS_OF, now=NOW)
        with pytest.raises(ScopeViolationError):
            assemble_context(db, auth, _req("kazna", "svod", br=5), today=TEST_AS_OF, now=NOW)
        with pytest.raises(ValidationFailed):
            assemble_context(db, auth, _req("kazna", "nope"), today=TEST_AS_OF, now=NOW)
