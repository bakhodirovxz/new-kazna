from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import anthropic
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai import probe
from app.ai.claude import ClaudeProvider
from app.core import integrations
from app.core.db import get_engine
from app.main import create_app
from tests.helpers import (
    SeedUser,
    clear_setting,
    create_user,
    issue_session,
    put_setting,
    use_session,
)

URL = "/api/v1/admin/integrations/ai/check"


class _Messages:
    def __init__(self, error: BaseException | None) -> None:
        self.error = error
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return SimpleNamespace(stop_reason="end_turn")


def _fake_provider(error: BaseException | None = None) -> tuple[ClaudeProvider, _Messages]:
    messages = _Messages(error)
    client = SimpleNamespace(messages=messages)
    provider = ClaudeProvider(client, model="claude-opus-5-5", effort="medium", max_tokens=8000)
    return provider, messages


@pytest.fixture
def admin_client() -> Iterator[Callable[[SeedUser], TestClient]]:
    clients: list[TestClient] = []

    def make(user: SeedUser) -> TestClient:
        client = TestClient(create_app(), base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        token, csrf, _ = issue_session(user.id)
        return use_session(client, token, csrf)

    yield make
    for client in clients:
        client.__exit__(None, None, None)
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.integration_checks WHERE name = 'ai'"))
    clear_setting("ai.enabled")


def test_probe_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ClaudeProvider, "from_config", classmethod(lambda cls, s, **kw: None))
    assert probe.ai_probe() == "not_configured"
    provider, messages = _fake_provider()
    monkeypatch.setattr(ClaudeProvider, "from_config", classmethod(lambda cls, s, **kw: provider))
    assert probe.ai_probe() == "ok"
    assert messages.kwargs["max_tokens"] == 16
    assert messages.kwargs["messages"][0]["content"] == "ping"
    auth = anthropic.AuthenticationError.__new__(anthropic.AuthenticationError)
    provider, _ = _fake_provider(auth)
    monkeypatch.setattr(ClaudeProvider, "from_config", classmethod(lambda cls, s, **kw: provider))
    assert probe.ai_probe() == "auth_failed"
    conn_err = anthropic.APIConnectionError.__new__(anthropic.APIConnectionError)
    provider, _ = _fake_provider(conn_err)
    monkeypatch.setattr(ClaudeProvider, "from_config", classmethod(lambda cls, s, **kw: provider))
    assert probe.ai_probe() == "connect_failed"


def test_api_check_records_result_without_secrets(
        monkeypatch: pytest.MonkeyPatch, admin_client: Callable[[SeedUser], TestClient]) -> None:
    provider, _ = _fake_provider()
    monkeypatch.setattr(ClaudeProvider, "from_config", classmethod(lambda cls, s, **kw: provider))
    put_setting("ai.enabled", True)
    client = admin_client(create_user("admin"))
    r = client.post(URL)
    assert r.status_code == 202, r.text
    body = r.json()
    assert (body["name"], body["status"], body["code"]) == ("ai", "ok", "ok")
    assert body["finished_at"] is not None
    got = client.get(f"/api/v1/admin/integrations/checks/{body['id']}").json()
    assert got["status"] == "ok"
    listing = client.get("/api/v1/admin/integrations").json()
    ai = next(i for i in listing if i["name"] == "ai")
    assert ai["check_in"] == "api" and [s["name"] for s in ai["secrets"]] == ["ai.api_key"]
    assert ai["secrets"][0]["state"] == "none"
    assert "ai_api_key" not in integrations.INTEGRATIONS["ai"].fields


def test_api_check_respects_enabled_and_cooldown(
        monkeypatch: pytest.MonkeyPatch, admin_client: Callable[[SeedUser], TestClient]) -> None:
    provider, messages = _fake_provider()
    monkeypatch.setattr(ClaudeProvider, "from_config", classmethod(lambda cls, s, **kw: provider))
    client = admin_client(create_user("admin"))
    r = client.post(URL)  # ai.enabled o'chiq — pulli chaqiruv yo'q
    assert (r.status_code, r.json()["error"]["code"]) == (404, "ai_disabled")
    assert messages.kwargs == {}
    put_setting("ai.enabled", True)
    assert client.post(URL).status_code == 202
    again = client.post(URL)  # 1 daqiqada bir marta
    assert again.status_code == 429 and int(again.headers["Retry-After"]) > 0
