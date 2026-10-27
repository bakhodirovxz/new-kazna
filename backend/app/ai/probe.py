"""«AI-анализ» integratsiyasini tekshirish (api tomonida, egress shu yerda): modelga 1 ta qisqa
so'rov — hech qanday ma'lumotsiz. Faqat xavfsiz kod qaytaradi (U8/U9): matn va istisno saqlanmaydi.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import anthropic

from app.ai.claude import ClaudeProvider, map_error
from app.core.config import get_settings

PROBE_TIMEOUT_S = 15.0
_CODE = {"ai_timeout": "timeout", "ai_unavailable": "connect_failed", "ai_busy": "http_error",
         "ai_misconfigured": "auth_failed", "ai_refused": "ok", "ai_failed": "error"}


async def _ping(provider: ClaudeProvider) -> str:
    try:
        await asyncio.wait_for(provider.client.messages.create(
            model=provider.model, max_tokens=16, output_config={"effort": "low"},
            messages=[{"role": "user", "content": "ping"}]), PROBE_TIMEOUT_S)
    except TimeoutError:
        return "timeout"
    except anthropic.APIError as exc:
        return _CODE.get(map_error(exc).code, "error")
    return "ok"


def ai_probe() -> str:
    provider = ClaudeProvider.from_config(get_settings())
    if provider is None:
        return "not_configured"
    return asyncio.run(_ping(provider))


API_PROBES: dict[str, Callable[[], str]] = {"ai": ai_probe}
