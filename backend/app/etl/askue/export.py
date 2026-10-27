"""АСКУЭ eksporti manbalari (S3 spec 3.1). Transport mijoz bilan kelishilmagan (TZ 8: «выгрузка
по расписанию или API»), shuning uchun protokol: DirectoryExport — worker'ga faqat o'qish uchun
ulangan katalog (/data/import/askue); AskueApiExport — «не настроен» stub'i.

Katalogdan oxirgi `max_age_days` kun ichida o'zgargan va yoshi ≥ `min_age` s bo'lgan *.csv
fayllar har yugurishda qayta o'qiladi: yuklash upsert (stansiya:sana kaliti) — idempotent, jurnal
va arxiv kerak emas; eski fayllarni host cron o'chiradi (docs/integration/askue-connector.md).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import ConfigError
from app.etl.types import ConnectorUnavailableError, HealthResult, Window

MAX_BYTES = 20 * 1024 * 1024
MIN_AGE_SECONDS = 60.0
ASKUE_API_MESSAGE = ("АСКУЭ API не настроен: формат и доступ не согласованы с заказчиком — "
                     "используйте выгрузку файлов в каталог /data/import/askue")


@dataclass(frozen=True, slots=True)
class ExportFile:
    name: str
    data: bytes
    error: str | None = None  # "too_large" — fayl o'qilmadi


class AskueExport(Protocol):
    name: str

    def healthcheck(self) -> HealthResult: ...

    def files(self, window: Window) -> Iterator[ExportFile]: ...


class DirectoryExport:
    name = "files"

    def __init__(self, inbox: Path, *, max_age_days: int = 7, min_age: float = MIN_AGE_SECONDS,
                 max_bytes: int = MAX_BYTES, now: Callable[[], float] = time.time) -> None:
        self.inbox = inbox
        self.max_age_days = max_age_days
        self.min_age = min_age
        self.max_bytes = max_bytes
        self.now = now

    def healthcheck(self) -> HealthResult:
        if self.inbox.is_dir():
            return HealthResult(True, f"АСКУЭ: каталог {self.inbox}")
        return HealthResult(False, f"АСКУЭ: каталог {self.inbox} не найден")

    def files(self, window: Window) -> Iterator[ExportFile]:
        if not self.inbox.is_dir():
            raise ConnectorUnavailableError(f"АСКУЭ: каталог {self.inbox} недоступен")
        now = self.now()
        oldest = now - self.max_age_days * 86400
        for path in sorted(self.inbox.iterdir()):
            if path.suffix.lower() != ".csv" or path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            if stat.st_mtime > now - self.min_age or stat.st_mtime < oldest:
                continue
            if stat.st_size > self.max_bytes:
                yield ExportFile(path.name, b"", "too_large")
                continue
            yield ExportFile(path.name, path.read_bytes())


class AskueNotConfigured(ConfigError):  # noqa: N818 — reja nomi
    """АСКУЭ API hali kelishilmagan (spec 12, ochiq savol 1)."""


class AskueApiExport:
    name = "api"

    def __init__(self) -> None:
        raise AskueNotConfigured(ASKUE_API_MESSAGE)

    def healthcheck(self) -> HealthResult:
        raise AskueNotConfigured(ASKUE_API_MESSAGE)

    def files(self, window: Window) -> Iterator[ExportFile]:
        raise AskueNotConfigured(ASKUE_API_MESSAGE)
