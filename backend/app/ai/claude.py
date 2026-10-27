"""Anthropic Claude provayderi — rasmiy `anthropic` Python SDK.

- Asinxron oqim: `messages.stream(...)` → `text_stream` → `get_final_message()`.
- Kalit, model, effort, max_tokens, fallbacks — HAR SO'ROVDA panel sozlamalaridan
  (`integrations.secret` + `sysconfig.current`); mijoz keshlanmaydi (kalit darhol almashadi).
- Adaptiv fikrlash, `output_config.effort`; `temperature`/`budget_tokens`/prefill yo'q.
- SDK qayta urinishlari o'chiq (`max_retries=0`): 60 s byudjetni servis o'zi nazorat qiladi.
- Rad etish zaxirasi: beta `server-side-fallback-2026-07-01` + `fallbacks: "default"`.
- HTTP mijozi — `DefaultAsyncHttpxClient` (1.x SDK `httpx2` ustida); proksi — standart
  `HTTPS_PROXY` muhiti (compose.ai.yml), CA — `AI_CA_FILE` mavjud bo'lsa.
- Prompt va javob matni log'ga yozilmaydi; xatoda faqat tur va so'rov id'si.
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import anthropic
from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient

from app.ai.provider import AI_TIMEOUT_S, AiProviderError, log
from app.core import integrations
from app.core.config import Settings
from app.core.db import get_engine

FALLBACK_BETA = "server-side-fallback-2026-07-01"
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


class ClaudeProvider:
    name = "anthropic"

    def __init__(self, client: Any, *, model: str, effort: str, max_tokens: int,
                 fallbacks: bool) -> None:
        self.client = client
        self.model = model
        self._effort = effort
        self._max_tokens = max_tokens
        self._fallbacks = fallbacks

    @classmethod
    def from_config(cls, settings: Settings) -> ClaudeProvider | None:
        """Kalit yo'q → None (funksiya «не настроен»)."""
        with get_engine("app").connect() as conn:
            key = integrations.secret(conn, "ai.api_key")
            cfg = integrations.field_values(conn, "ai")
        if not key:
            return None
        ca = Path(settings.ai_ca_file)
        verify: Any = ssl.create_default_context(cafile=str(ca)) if ca.is_file() else True
        client = AsyncAnthropic(
            api_key=key, base_url=settings.ai_base_url or None, max_retries=0,
            timeout=anthropic.Timeout(AI_TIMEOUT_S, connect=10.0),
            http_client=DefaultAsyncHttpxClient(verify=verify))
        return cls(client, model=str(cfg["ai.model"]), effort=str(cfg["ai.effort"]),
                   max_tokens=int(cfg["ai.max_tokens"]), fallbacks=bool(cfg["ai.fallbacks"]))

    def request(self, system: str, prompt: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self._effort},
        }
        if self._fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["extra_body"] = {"fallbacks": "default"}
        return params

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        params = self.request(system, prompt)
        messages = self.client.beta.messages if self._fallbacks else self.client.messages
        try:
            async with messages.stream(**params) as stream:
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
