from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.audit.service import AuditAction
from app.auth.permissions import Perm
from app.core import integrations, sysconfig
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import MESSAGES, AiDisabledError, AiLimitError
from app.dwh.reference import DEFAULT_SETTINGS, validate_setting


def test_ai_config_defaults() -> None:
    s = get_settings()
    assert (s.ai_provider, s.ai_base_url) == ("anthropic", "")
    assert s.ai_ca_file == "/run/secrets/ai_ca_bundle"
    assert not hasattr(s, "ai_api_key")  # U6: kalit faqat integrations orqali


@pytest.mark.parametrize(("update", "needle"), [
    ({"ai_provider": "fake", "env": "prod"}, "AI_PROVIDER=fake"),
    ({"ai_base_url": "http://gw.local"}, "AI_BASE_URL"),
])
def test_ai_config_problems(update: dict[str, Any], needle: str) -> None:
    problems = get_settings().model_copy(update=update).problems()
    assert any(needle in p for p in problems), problems


def test_ai_config_ok_variants() -> None:
    base = get_settings()
    for update in ({"ai_provider": "fake"}, {"ai_base_url": "https://gw.local"}):
        problems = base.model_copy(update=update).problems()
        assert not any("AI_" in p for p in problems), (update, problems)


def test_ai_settings() -> None:
    assert DEFAULT_SETTINGS["ai.enabled"] is False
    assert (DEFAULT_SETTINGS["ai.user_per_hour"], DEFAULT_SETTINGS["ai.org_per_day"]) == (20, 300)
    assert validate_setting("ai.enabled", True) is True
    assert validate_setting("ai.org_per_day", 1000) == 1000
    for key, value in (("ai.enabled", "yes"), ("ai.enabled", 1), ("ai.user_per_hour", 0),
                       ("ai.org_per_day", 100001), ("ai.model", "Claude Opus!"),
                       ("ai.effort", "max"), ("ai.max_tokens", 500), ("ai.fallbacks", "x")):
        with pytest.raises(ValueError):
            validate_setting(key, value)
    for key in ("ai.enabled", "ai.user_per_hour", "ai.org_per_day"):
        d = sysconfig.REGISTRY[key]
        assert (d.category, d.perm, d.guarded) == ("ai", Perm.ADMIN_SECURITY, True)
    assert DEFAULT_SETTINGS["ai.model"] == "claude-opus-5-5"
    assert (DEFAULT_SETTINGS["ai.effort"], DEFAULT_SETTINGS["ai.max_tokens"],
            DEFAULT_SETTINGS["ai.fallbacks"]) == ("medium", 8000, True)


def test_ai_integration_registered() -> None:
    integ = integrations.INTEGRATIONS["ai"]
    assert integ.check_in == "api" and integ.endpoint == ()
    assert [s.name for s in integ.secrets] == ["ai.api_key"]
    assert set(integ.fields) == {"ai.model", "ai.effort", "ai.max_tokens", "ai.fallbacks"}
    for key in integ.fields:
        assert sysconfig.REGISTRY[key].perm == Perm.ADMIN_INTEGRATIONS


def test_ai_errors_and_audit_actions() -> None:
    limit = AiLimitError(120, "org")
    assert (limit.status_code, limit.code) == (429, "ai_limit")
    assert limit.headers == {"Retry-After": "120"}
    assert limit.params == {"retry_after": 120, "scope": "org"}
    disabled = AiDisabledError()
    assert (disabled.status_code, disabled.code) == (404, "ai_disabled")
    for code in ("ai_disabled", "ai_limit", "ai_question_sensitive", "ai_context_rejected"):
        assert code in MESSAGES
    assert AuditAction.AI_REQUEST.value == "ai.request"
    assert AuditAction.AI_JOURNAL_PURGED.value == "ai.journal.purged"


def test_ai_requests_grants() -> None:
    with get_engine("app").connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("SELECT count(*) FROM core.ai_requests")).scalar_one()
            with pytest.raises(ProgrammingError):
                conn.execute(text("DELETE FROM core.ai_requests"))
        finally:
            tx.rollback()
    with get_engine("etl").connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("DELETE FROM core.ai_requests WHERE false"))
        finally:
            tx.rollback()


def test_anthropic_sdk_installed() -> None:
    import anthropic

    for name in ("AsyncAnthropic", "DefaultAsyncHttpxClient", "Timeout", "APIError",
                 "APIStatusError", "APIConnectionError", "APITimeoutError", "RateLimitError"):
        assert hasattr(anthropic, name), name
