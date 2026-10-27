"""Soxta AI provayderi — faqat dev/test va E2E (`AI_PROVIDER=fake`; prod'da rad etiladi).

Tarmoqqa chiqmaydi. Standart javob TZ 7 tuzilmasida (3 blok) — UI oqimini tekshirish uchun.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.ai.provider import AiProviderError

DEFAULT_ANSWER = (
    "## Что важно заметить\n"
    "- Демонстрационный ответ: сводка страницы получена ({chars} символов).\n"
    "- Суммы в ответе называются в млрд или трлн сум.\n"
    "- Реальный анализ появится после подключения провайдера.\n\n"
    "## Риски и отклонения\n"
    "- В демонстрационном режиме выводы по данным не формируются.\n\n"
    "## Действия на ближайшие две недели\n"
    "- Согласовать подключение AI-анализа со службой информационной безопасности.\n"
)


def _split(text: str, size: int = 40) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, chunks: list[str] | None = None, *, delay: float = 0.0,
                 error: str | None = None, error_after: int = 0) -> None:
        self.chunks = chunks
        self.delay = delay
        self.error = error
        self.error_after = error_after
        self.calls: list[tuple[str, str]] = []
        self.closed = 0

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        self.calls.append((system, prompt))
        parts = self.chunks if self.chunks is not None else _split(
            DEFAULT_ANSWER.format(chars=len(prompt)))
        try:
            for index, part in enumerate(parts):
                if self.error is not None and index == self.error_after:
                    raise AiProviderError(self.error)
                if self.delay:
                    await asyncio.sleep(self.delay)
                yield part
            if self.error is not None and self.error_after >= len(parts):
                raise AiProviderError(self.error)
        finally:
            self.closed += 1
