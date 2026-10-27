"""AI provayder abstraksiyasi (S5 spec 4.3).

`AiProvider` — oqimli matn manbai. Hozir bitta haqiqiy implementatsiya (`ClaudeProvider`,
rasmiy Anthropic SDK) va dev/test uchun `FakeProvider`. On-prem/OpenAI-mos endpoint keyinchalik
shu protokolni amalga oshiradi — hozir faqat konfiguratsiya o'rni (`AI_PROVIDER=openai_compatible`
→ funksiya o'chiq, ogohlantirish).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

AI_TIMEOUT_S = 60.0  # TZ 7: «Тайм-аут 60 секунд, с кнопкой отмены»
ERROR_CODES = ("ai_timeout", "ai_unavailable", "ai_busy", "ai_refused", "ai_misconfigured",
               "ai_failed")
log = get_logger("ugekazna.ai")


class AiProviderError(Exception):
    """Provayder xatosi — foydalanuvchiga `ERROR_CODES` dan biri (tafsilot log'da, matnsiz)."""

    def __init__(self, code: str) -> None:
        self.code = code if code in ERROR_CODES else "ai_failed"
        super().__init__(self.code)


class AiProvider(Protocol):
    name: str
    model: str

    def stream(self, system: str, prompt: str) -> AsyncIterator[str]: ...


def build_provider(settings: Settings) -> AiProvider | None:
    if settings.ai_provider == "fake":
        if settings.env == "prod":
            return None  # problems() ham rad etadi — ikki qavatli himoya
        from app.ai.fake import FakeProvider

        return FakeProvider(delay=0.05)
    if settings.ai_provider == "openai_compatible":
        log.warning("ai_provider_not_implemented", provider=settings.ai_provider)
        return None
    from app.ai.claude import ClaudeProvider

    return ClaudeProvider.from_config(settings)


def get_ai_provider() -> AiProvider | None:
    """FastAPI dependency (testlarda `dependency_overrides`). Kalit/model har so'rovda o'qiladi:
    panelda kalit almashsa, eski mijoz ishlatilmaydi."""
    return build_provider(get_settings())
