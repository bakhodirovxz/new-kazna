"""Anthropic Claude provayderi — rasmiy `anthropic` Python SDK.

- Asinxron oqim: `messages.stream(...)` → `text_stream` → `get_final_message()`.
- Model, effort, max_tokens — HAR SO'ROVDA panel sozlamalaridan; model QOTIRILGAN: serverning
  rad etish zaxirasi (boshqa modelga yo'naltirish) ishlatilmaydi: ma'lumot faqat shu modelga ketadi.
- Kalit faqat birinchi chaqiruvda ochiladi (`/ai/status` ochmaydi); mijoz jarayon bo'yicha bitta
  (kalit almashsa — yangi mijoz), `AI_CA_FILE` bo'sh yoki yo'q bo'lsa — tizim CA'lari.
- Adaptiv fikrlash, `output_config.effort`; `temperature`/`budget_tokens`/prefill yo'q.
- SDK qayta urinishlari o'chiq (`max_retries=0`): 60 s byudjetni servis o'zi nazorat qiladi.
- Proksi — standart `HTTPS_PROXY` muhiti (compose.ai.yml).
- Prompt va javob matni log'ga yozilmaydi; xatoda faqat tur va so'rov id'si.
"""

from __future__ import annotations

import hashlib
import ssl
import threading
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import anthropic
from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient

from app.ai.provider import AI_TIMEOUT_S, AiProviderError, log
from app.core import integrations
from app.core.config import Settings
from app.core.db import get_engine

TRUNCATED_NOTE = "\n\n_(ответ сокращён: достигнут предел длины)_"


def map_error(exc: BaseException) -> AiProviderError:
    if isinstance(exc, anthropic.APITimeoutError):
        return AiProviderError("ai_timeout")
    if isinstance(exc, anthropic.APIConnectionError):
        return AiProviderError("ai_unavailable")
    if isinstance(exc, anthropic.RateLimitError):
        return AiProviderError("ai_busy")
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                        anthropic.NotFoundError, anthropic.BadRequestError)):
        return AiProviderError("ai_misconfigured")
    if isinstance(exc, anthropic.APIStatusError):
        status = int(getattr(exc, "status_code", 0) or 0)
        return AiProviderError("ai_unavailable" if status >= 500 else "ai_failed")
    return AiProviderError("ai_failed")


def ca_context(path: str) -> ssl.SSLContext | bool:
    """Bo'sh yoki yo'q CA fayli — tizim CA'lari (compose.ai.yml bo'sh `ai_ca_bundle.pem` beradi)."""
    ca = Path(path) if path else None
    if ca is not None and ca.is_file() and ca.stat().st_size > 0:
        return ssl.create_default_context(cafile=str(ca))
    return True


_lock = threading.Lock()
_shared: tuple[str, Any] | None = None  # (kalit izi, mijoz): jarayon bo'yicha bitta mijoz


def build_client(settings: Settings, key: str) -> AsyncAnthropic:
    return AsyncAnthropic(
        api_key=key, base_url=settings.ai_base_url or None, max_retries=0,
        timeout=anthropic.Timeout(AI_TIMEOUT_S, connect=10.0),
        http_client=DefaultAsyncHttpxClient(verify=ca_context(settings.ai_ca_file)))


def shared_client(settings: Settings) -> Any:
    """Kalit shu yerda ochiladi; o'zgarmasa mavjud mijoz qayta ishlatiladi."""
    global _shared
    with get_engine("app").connect() as conn:
        key = integrations.secret(conn, "ai.api_key")
    if not key:
        raise AiProviderError("ai_misconfigured")
    fingerprint = hashlib.sha256(f"{key}|{settings.ai_base_url}|{settings.ai_ca_file}".encode()
                                 ).hexdigest()
    with _lock:
        if _shared is None or _shared[0] != fingerprint:
            _shared = (fingerprint, build_client(settings, key))
        return _shared[1]


class ClaudeProvider:
    name = "anthropic"

    def __init__(self, client: Any = None, *, model: str, effort: str, max_tokens: int,
                 client_factory: Callable[[], Any] | None = None) -> None:
        self._client = client
        self._factory = client_factory
        self.model = model
        self._effort = effort
        self._max_tokens = max_tokens

    @property
    def client(self) -> Any:
        if self._client is None:
            if self._factory is None:
                raise AiProviderError("ai_misconfigured")
            self._client = self._factory()
        return self._client

    def warm(self) -> None:
        """Kalit/mijozni threadpool'da tayyorlash — event loop DB'da bloklanmasin."""
        _ = self.client

    @classmethod
    def from_config(cls, settings: Settings, *, shared: bool = True) -> ClaudeProvider | None:
        """Kalit yo'q → None. Kalit bu yerda OCHILMAYDI (faqat holat o'qiladi)."""
        with get_engine("app").connect() as conn:
            state = integrations.secret_state(conn, "ai.api_key")[0]
            cfg = integrations.field_values(conn, "ai")
        if state == "none":
            return None

        def factory() -> Any:
            if shared:
                return shared_client(settings)
            with get_engine("app").connect() as conn:
                return build_client(settings, integrations.secret(conn, "ai.api_key"))

        return cls(model=str(cfg["ai.model"]), effort=str(cfg["ai.effort"]),
                   max_tokens=int(cfg["ai.max_tokens"]), client_factory=factory)

    def request(self, system: str, prompt: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self._effort},
        }

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        params = self.request(system, prompt)
        try:
            async with self.client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text
                final = await stream.get_final_message()
        except anthropic.APIError as exc:
            log.warning("ai_provider_error", error=type(exc).__name__,
                        request_id=getattr(exc, "request_id", None))
            raise map_error(exc) from None
        if final.stop_reason == "refusal":
            raise AiProviderError("ai_refused")
        if final.stop_reason == "max_tokens":
            yield TRUNCATED_NOTE
