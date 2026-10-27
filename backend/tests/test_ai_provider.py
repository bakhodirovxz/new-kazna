from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import anthropic
import pytest

from app.ai import claude as claude_module
from app.ai.claude import TRUNCATED_NOTE, ClaudeProvider, ca_context, map_error
from app.ai.fake import DEFAULT_ANSWER, FakeProvider
from app.ai.provider import AiProviderError, build_provider
from app.core import integrations
from app.core.config import get_settings
from app.core.db import get_engine
from tests.helpers import clear_setting, put_setting


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _Stream:
    """`client.messages.stream(...)` ning soxta nusxasi (async context manager)."""

    def __init__(self, parts: list[str], stop: str, error: BaseException | None = None) -> None:
        self.parts, self.stop, self.error = parts, stop, error
        self.exited = False

    async def __aenter__(self) -> "_Stream":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        self.exited = True
        return False

    @property
    def text_stream(self) -> AsyncIterator[str]:
        async def gen() -> AsyncIterator[str]:
            for part in self.parts:
                yield part
            if self.error is not None:
                raise self.error
        return gen()

    async def get_final_message(self) -> Any:
        return SimpleNamespace(stop_reason=self.stop)


class _Messages:
    def __init__(self, stream: _Stream) -> None:
        self._stream = stream
        self.kwargs: dict[str, Any] | None = None

    def stream(self, **kwargs: Any) -> _Stream:
        self.kwargs = kwargs
        return self._stream


class _Client:
    def __init__(self, stream: _Stream) -> None:
        self.messages = _Messages(stream)
        self.beta = SimpleNamespace(messages=_Messages(stream))


def _provider(stream: _Stream) -> tuple[ClaudeProvider, _Client]:
    client = _Client(stream)
    return ClaudeProvider(client, model="claude-opus-5-5", effort="medium",
                          max_tokens=8000), client


async def _collect(provider: Any, system: str = "SYS", prompt: str = "PROMPT") -> list[str]:
    return [part async for part in provider.stream(system, prompt)]


@pytest.mark.anyio
async def test_request_pins_model_without_server_fallback() -> None:
    stream = _Stream(["Ответ ", "готов"], "end_turn")
    provider, client = _provider(stream)
    assert await _collect(provider) == ["Ответ ", "готов"]
    assert client.beta.messages.kwargs is None  # beta/fallbacks namespace ishlatilmaydi
    assert client.messages.kwargs == {
        "model": "claude-opus-5-5", "max_tokens": 8000, "system": "SYS",
        "messages": [{"role": "user", "content": "PROMPT"}],
        "thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"},
    }
    assert not {"betas", "extra_body", "temperature", "top_p", "top_k"} & set(
        client.messages.kwargs)
    assert stream.exited


@pytest.mark.anyio
async def test_refusal_raises_after_partial_text() -> None:
    provider, _ = _provider(_Stream(["Частичный "], "refusal"))
    got: list[str] = []
    with pytest.raises(AiProviderError) as exc:
        async for part in provider.stream("s", "p"):
            got.append(part)
    assert got == ["Частичный "] and exc.value.code == "ai_refused"


@pytest.mark.anyio
async def test_max_tokens_appends_note() -> None:
    provider, _ = _provider(_Stream(["Длинный ответ"], "max_tokens"))
    assert await _collect(provider) == ["Длинный ответ", TRUNCATED_NOTE]


@pytest.mark.anyio
async def test_sdk_error_inside_stream_is_mapped() -> None:
    error = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
    provider, _ = _provider(_Stream(["a"], "end_turn", error=error))
    with pytest.raises(AiProviderError) as exc:
        await _collect(provider)
    assert exc.value.code == "ai_busy"


def _exc(cls: type[BaseException], **attrs: Any) -> BaseException:
    instance = cls.__new__(cls)
    for key, value in attrs.items():
        setattr(instance, key, value)
    return instance


@pytest.mark.parametrize(("exc", "code"), [
    (_exc(anthropic.APITimeoutError), "ai_timeout"),
    (_exc(anthropic.APIConnectionError), "ai_unavailable"),
    (_exc(anthropic.RateLimitError), "ai_busy"),
    (_exc(anthropic.AuthenticationError), "ai_misconfigured"),
    (_exc(anthropic.PermissionDeniedError), "ai_misconfigured"),
    (_exc(anthropic.NotFoundError), "ai_misconfigured"),
    (_exc(anthropic.BadRequestError), "ai_misconfigured"),
    (_exc(anthropic.APIStatusError, status_code=529), "ai_unavailable"),
    (_exc(anthropic.APIStatusError, status_code=409), "ai_failed"),
    (ValueError("x"), "ai_failed"),
])
def test_error_mapping(exc: BaseException, code: str) -> None:
    assert map_error(exc).code == code


def test_provider_error_unknown_code_normalised() -> None:
    assert AiProviderError("whatever").code == "ai_failed"


def test_build_provider_and_key_from_integration() -> None:
    base = get_settings()
    fake = build_provider(base.model_copy(update={"ai_provider": "fake", "env": "dev"}))
    assert isinstance(fake, FakeProvider)
    assert build_provider(base.model_copy(update={"ai_provider": "fake", "env": "prod"})) is None
    assert build_provider(base.model_copy(update={"ai_provider": "openai_compatible"})) is None
    # kalit yo'q → None; panelda kalit + model → ClaudeProvider (tarmoqsiz, faqat konstruktsiya)
    assert build_provider(base) is None
    put_setting("ai.model", "claude-sonnet-5-5")
    try:
        with get_engine("app").begin() as conn:
            integrations.store_secret(conn, "ai.api_key", "sk-ant-test-key", None)
        provider = build_provider(base)
        assert isinstance(provider, ClaudeProvider) and provider.model == "claude-sonnet-5-5"
        assert claude_module.ClaudeProvider.from_config(base) is not None
    finally:
        with get_engine("app").begin() as conn:
            integrations.clear_secret(conn, "ai.api_key")
        clear_setting("ai.model")


@pytest.mark.anyio
async def test_fake_provider_behaviour() -> None:
    fake = FakeProvider()
    text = "".join(await _collect(fake, prompt="x" * 42))
    assert text == DEFAULT_ANSWER.format(chars=42)
    for heading in ("## Что важно заметить", "## Риски и отклонения",
                    "## Действия на ближайшие две недели"):
        assert heading in text
    assert fake.calls == [("SYS", "x" * 42)] and fake.closed == 1
    failing = FakeProvider(["a", "b"], error="ai_timeout", error_after=1)
    got: list[str] = []
    with pytest.raises(AiProviderError) as exc:
        async for part in failing.stream("s", "p"):
            got.append(part)
    assert got == ["a"] and exc.value.code == "ai_timeout" and failing.closed == 1


def test_ca_context_empty_missing_and_real(tmp_path: Any) -> None:
    empty = tmp_path / "empty.pem"
    empty.write_text("")
    assert ca_context(str(empty)) is True  # bo'sh fayl — tizim CA'lari (I1)
    assert ca_context(str(tmp_path / "missing.pem")) is True
    assert ca_context("") is True


def test_shared_client_reused_and_key_not_decrypted_for_status(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    from app.ai import claude as mod

    built: list[str] = []
    monkeypatch.setattr(mod, "build_client", lambda s, key: built.append(key) or object())
    monkeypatch.setattr(mod, "_shared", None)
    opened: list[int] = []
    real_secret = integrations.secret
    monkeypatch.setattr(integrations, "secret",
                        lambda conn, name: opened.append(1) or real_secret(conn, name))
    try:
        with get_engine("app").begin() as conn:
            integrations.store_secret(conn, "ai.api_key", "sk-ant-test-key", None)
        base = get_settings().model_copy(update={"ai_ca_file": str(tmp_path / "none")})
        provider = ClaudeProvider.from_config(base)
        assert provider is not None and opened == []  # holat o'qildi, kalit ochilmadi
        first = ClaudeProvider.from_config(base)
        assert first is not None
        assert first.client is provider.client and len(built) == 1  # bitta mijoz
        with get_engine("app").begin() as conn:
            integrations.store_secret(conn, "ai.api_key", "sk-ant-other-key", None)
        again = ClaudeProvider.from_config(base)
        assert again is not None and again.client is not provider.client and len(built) == 2
    finally:
        with get_engine("app").begin() as conn:
            integrations.clear_secret(conn, "ai.api_key")
