import asyncio
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai import journal
from app.ai.fake import FakeProvider
from app.ai.provider import AiProvider, get_ai_provider
from app.ai.service import Job, stream_events
from app.core.db import get_engine
from app.etl.db import etl_transaction
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF
from tests.helpers import (
    SeedUser,
    clear_setting,
    create_user,
    issue_session,
    put_setting,
    use_session,
)

URL = "/api/v1/ai/analyze"
OBZOR = {"section": "obzor", "page": "svod"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM core.ai_requests"))
    yield
    for key in ("ai.enabled", "ai.user_per_hour"):
        clear_setting(key)


@pytest.fixture
def enabled() -> None:
    put_setting("ai.enabled", True)


@pytest.fixture
def make_client() -> Iterator[Callable[[AiProvider | None, SeedUser], TestClient]]:
    clients: list[TestClient] = []

    def make(provider: AiProvider | None, user: SeedUser) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_ai_provider] = lambda: provider
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        token, csrf, _ = issue_session(user.id)
        return use_session(client, token, csrf)

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def events(body: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for frame in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def _journal() -> list[dict[str, Any]]:
    with get_engine("app").connect() as conn:
        return [dict(r) for r in conn.execute(text(
            "SELECT * FROM core.ai_requests ORDER BY id")).mappings()]


def _audit(action: str) -> list[dict[str, Any]]:
    with get_engine("app").connect() as conn:
        return [dict(r) for r in conn.execute(text(
            "SELECT result, object_id, details FROM core.audit_log WHERE action = :a "
            "ORDER BY id"), {"a": action}).mappings()]


@pytest.mark.usefixtures("published_synthetic")
def test_disabled_by_default(make_client: Any) -> None:
    provider = FakeProvider(["x"])
    client = make_client(provider, create_user("rukovodstvo"))
    status = client.get("/api/v1/ai/status").json()
    assert (status["enabled"], status["reason"]) == (False, "disabled")
    assert (status["user_per_hour"], status["org_per_day"]) == (20, 300)
    r = client.post(URL, json=OBZOR)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "ai_disabled")
    assert provider.calls == [] and _journal() == []


@pytest.mark.usefixtures("published_synthetic", "enabled")
def test_enabled_without_provider_is_not_configured(make_client: Any) -> None:
    client = make_client(None, create_user("rukovodstvo"))
    assert client.get("/api/v1/ai/status").json()["reason"] == "not_configured"
    assert client.post(URL, json=OBZOR).status_code == 404


@pytest.mark.usefixtures("published_synthetic", "enabled")
def test_stream_events_journal_and_audit(make_client: Any) -> None:
    provider = FakeProvider(["## Что важно заметить\n", "- Остаток **1,2 трлн сум**\n"])
    user = create_user("rukovodstvo")
    client = make_client(provider, user)
    r = client.post(URL, json={**OBZOR, "per": "ytd"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-store"
    got = events(r.text)
    assert [e for e, _ in got] == ["start", "delta", "delta", "done"]
    request_id = got[0][1]["request_id"]
    assert got[-1][1] == {"length": len("## Что важно заметить\n- Остаток **1,2 трлн сум**\n")}
    (row,) = _journal()
    assert (row["id"], row["status"], row["user_id"], row["section"]) == (
        request_id, "ok", user.id, "obzor")
    assert row["answer_chars"] == got[-1][1]["length"] and row["context_chars"] > 0
    assert row["filters"] == {"br": None, "per": "ytd"} and row["finished_at"] is not None
    system, prompt = provider.calls[0]
    assert "## Что важно заметить" in system
    assert prompt.startswith("<данные>\n") and "Проанализируй показатели страницы." in prompt
    audit = _audit("ai.request")[-1]
    assert (audit["result"], audit["object_id"]) == ("ok", str(request_id))
    assert audit["details"]["section"] == "obzor" and "question" not in audit["details"]
    assert client.get("/api/v1/ai/status").json()["used_last_hour"] == 1


@pytest.mark.usefixtures("published_synthetic", "enabled")
def test_question_preset_and_validation(make_client: Any) -> None:
    provider = FakeProvider(["ok"])
    client = make_client(provider, create_user("rukovodstvo"))
    body = {"section": "kazna", "page": "svod", "question": "Почему вырос долг?"}
    assert client.post(URL, json=body).status_code == 200
    assert "<вопрос>\nПочему вырос долг?\n</вопрос>" in provider.calls[-1][1]
    assert _journal()[-1]["question"] == "Почему вырос долг?"
    assert client.post(URL, json={"section": "kazna", "page": "svod",
                                  "preset": "risks"}).status_code == 200
    assert "Какие главные риски?" in provider.calls[-1][1]
    both = client.post(URL, json={**body, "preset": "risks"})
    assert both.status_code == 422
    inn = client.post(URL, json={**body, "question": "Кто владелец ИНН 301234567?"})
    assert (inn.status_code, inn.json()["error"]["code"]) == (422, "ai_question_sensitive")
    assert len(_journal()) == 2


@pytest.mark.usefixtures("published_synthetic", "enabled")
def test_forbidden_section_scope_and_unknown_page(make_client: Any) -> None:
    economist = make_client(FakeProvider(["x"]),
                            create_user("economist_filiala", branch_ids=(3,)))
    r = economist.post(URL, json={"section": "kredity", "page": "svod"})
    assert (r.status_code, r.json()["error"]["code"]) == (403, "forbidden")
    r = economist.post(URL, json={"section": "kazna", "page": "svod", "br": 5})
    assert (r.status_code, r.json()["error"]["code"]) == (403, "scope_violation")
    admin = make_client(FakeProvider(["x"]), create_user("rukovodstvo"))
    assert admin.post(URL, json={"section": "kazna", "page": "nope"}).status_code == 422
    assert _journal() == []


@pytest.mark.usefixtures("published_synthetic", "enabled")
def test_rate_limit_user(make_client: Any) -> None:
    put_setting("ai.user_per_hour", 1)
    client = make_client(FakeProvider(["x"]), create_user("rukovodstvo"))
    assert client.post(URL, json=OBZOR).status_code == 200
    r = client.post(URL, json=OBZOR)
    assert r.status_code == 429
    error = r.json()["error"]
    assert error["code"] == "ai_limit" and error["params"]["scope"] == "user"
    assert int(r.headers["Retry-After"]) == error["params"]["retry_after"] > 3500
    assert _audit("ai.request")[-1]["result"] == "denied"


@pytest.mark.usefixtures("published_synthetic", "enabled")
def test_provider_error_event(make_client: Any) -> None:
    provider = FakeProvider(["Частичный ответ"], error="ai_refused", error_after=1)
    client = make_client(provider, create_user("rukovodstvo"))
    got = events(client.post(URL, json=OBZOR).text)
    assert [e for e, _ in got] == ["start", "delta", "error"]
    assert got[-1][1]["code"] == "ai_refused" and got[-1][1]["message"]
    assert (_journal()[-1]["status"], _journal()[-1]["error_code"]) == ("refused", "ai_refused")


def _job(provider: FakeProvider) -> Job:
    user = create_user("rukovodstvo")
    request_id = journal.reserve(journal.NewRequest(
        user.id, "obzor", "svod", {}, None, None, 10, provider.name, provider.model),
        now=datetime.now(UTC))
    return Job(request_id, "SYS", "PROMPT", provider)


@pytest.mark.anyio
async def test_timeout_closes_provider_and_journals() -> None:
    provider = FakeProvider(["a", "b"], delay=0.5)
    job = _job(provider)
    frames = [f async for f in stream_events(job, timeout=0.1)]
    got = events(b"".join(frames).decode())
    assert [e for e, _ in got] == ["start", "error"] and got[-1][1]["code"] == "ai_timeout"
    await asyncio.sleep(0)
    assert provider.closed == 1
    row = _journal()[-1]
    assert (row["status"], row["error_code"]) == ("timeout", "ai_timeout")


@pytest.mark.anyio
async def test_client_disconnect_marks_cancelled() -> None:
    provider = FakeProvider(["a", "b", "c"], delay=0.01)
    job = _job(provider)
    stream = stream_events(job)
    first = [await anext(stream), await anext(stream)]  # start + birinchi delta
    await stream.aclose()  # brauzer AbortController / tarmoq uzilishi
    assert b"event: delta" in first[1]
    row = _journal()[-1]
    assert (row["status"], row["answer_chars"]) == ("cancelled", 1)
    assert provider.closed == 1


@pytest.mark.usefixtures("published_synthetic", "enabled")
def test_journal_endpoint_for_auditors(make_client: Any) -> None:
    make_client(FakeProvider(["x"]), create_user("rukovodstvo")).post(
        URL, json={**OBZOR, "question": "Итоги месяца?"})
    auditor = make_client(None, create_user("vnutr_kontrol"))
    page = auditor.get("/api/v1/audit/ai-requests").json()
    assert page["total"] == 1 and page["items"][0]["question"] == "Итоги месяца?"
    assert page["items"][0]["username"] and page["items"][0]["status"] == "ok"
    economist = make_client(None, create_user("economist_filiala", branch_ids=(3,)))
    assert economist.get("/api/v1/audit/ai-requests").status_code == 403


@pytest.mark.usefixtures("published_synthetic", "enabled")
def test_over_limit_request_builds_no_context(
        make_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    put_setting("ai.user_per_hour", 1)
    client = make_client(FakeProvider(["x"]), create_user("rukovodstvo"))
    assert client.post(URL, json=OBZOR).status_code == 200

    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("kontekst qurilmasligi kerak")

    monkeypatch.setattr("app.ai.service.assemble_context", boom)
    r = client.post(URL, json=OBZOR)
    assert r.status_code == 429 and r.json()["error"]["code"] == "ai_limit"


@pytest.mark.usefixtures("enabled")
def test_status_with_empty_ca_file_and_stored_key(
        tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """compose.ai.yml bo'sh ai_ca_bundle.pem beradi — /ai/status 500 bermasligi kerak (I1)."""
    from app.ai import provider as provider_module
    from app.core import integrations
    from app.core.config import get_settings

    empty = tmp_path / "ai_ca_bundle.pem"
    empty.write_text("")
    settings = get_settings().model_copy(update={"ai_ca_file": str(empty)})
    monkeypatch.setattr(provider_module, "get_settings", lambda: settings)
    user = create_user("rukovodstvo")
    app = create_app()
    try:
        with get_engine("app").begin() as conn:
            integrations.store_secret(conn, "ai.api_key", "sk-ant-test-key", None)
        with TestClient(app, base_url="https://testserver") as client:
            token, csrf, _ = issue_session(user.id)
            use_session(client, token, csrf)
            r = client.get("/api/v1/ai/status")
            assert r.status_code == 200 and r.json()["enabled"] is True
    finally:
        with get_engine("app").begin() as conn:
            integrations.clear_secret(conn, "ai.api_key")
