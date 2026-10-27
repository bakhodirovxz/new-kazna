"""BankFileConnector — SourceConnector (S2 spec 3.2): /data/import/banks/<bank>/*.csv.

Inbox faqat o'qish uchun ulangan: fayl o'chirilmaydi, balki arxivga baytma-bayt nusxalanadi
(<archive>/<bank>/<YYYY-MM>/<sha256>.csv) va core.bank_files jurnaliga yoziladi. Faqat yoshi
≥ min_age va hajmi ≤ max_bytes bo'lgan `*.csv` o'qiladi (yuklanayotgan fayl o'qilmaydi).
Maqsadlar «to'liq berilgan» emas (by_target bo'sh): fayllar inkremental, oldingi ko'chirmalar
o'chirilmaydi — faqat idempotent upsert.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.etl.banks.accounts import AccountIndex
from app.etl.banks.adapters import ADAPTERS
from app.etl.banks.fx import DbFxLookup, FxLookup
from app.etl.banks.ledger import DbFileLedger, FileEntry, FileLedger
from app.etl.banks.mapper import BankMapper
from app.etl.banks.models import BankFileError, mask
from app.etl.banks.registry import BANKS, BankAccount
from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    ReportingSink,
    StagingSink,
    Watermark,
    Window,
)

MAX_BYTES = 50 * 1024 * 1024
MIN_AGE_SECONDS = 60.0
log = get_logger("ugekazna.banks")


class BankFileConnector:
    def __init__(self, inbox: Path, archive: Path, accounts: Sequence[BankAccount], *,
                 formats: Mapping[str, str] | None = None, ledger: FileLedger | None = None,
                 fx: FxLookup | None = None, source: str = "banks",
                 index_key: bytes | None = None, min_age: float = MIN_AGE_SECONDS,
                 max_bytes: int = MAX_BYTES, now: Callable[[], float] = time.time) -> None:
        self.source = source
        self.inbox = inbox
        self.archive = archive
        self.accounts = list(accounts)
        self.formats = dict(formats or {})
        self.ledger: FileLedger = ledger or DbFileLedger()
        self.fx: FxLookup = fx or DbFxLookup()
        self.index_key = index_key or get_settings().key_bytes("blind_index_key")
        self.min_age = min_age
        self.max_bytes = max_bytes
        self.now = now

    # ── Protokol ────────────────────────────────────────────────────
    def healthcheck(self) -> HealthResult:
        if not self.inbox.is_dir() or not os.access(self.inbox, os.R_OK | os.X_OK):
            return HealthResult(False, "каталог банковских выписок недоступен")
        if not self.archive.is_dir() or not os.access(self.archive, os.W_OK | os.X_OK):
            return HealthResult(False, "архив банковских выписок недоступен для записи")
        return HealthResult(True, "banks")

    def watermark(self) -> Watermark:
        return Watermark(datetime.now(UTC))

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None  # ko'chirma o'zini o'zi tekshiradi (OB + oborot = CB, mapper'da)

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        if not isinstance(sink, ReportingSink):
            raise TypeError("BankFileConnector: ReportingSink kerak (xatolar core.etl_error ga)")
        mapper = BankMapper(sink, AccountIndex(self.accounts, self.index_key), self.fx,
                            index_key=self.index_key)
        total = 0
        for bank_code, path in self._candidates():
            display = mask(f"{bank_code}/{path.name}")
            size = path.stat().st_size
            if size > self.max_bytes:
                mapper.report(display, "too_large",
                              f"файл больше {self.max_bytes // (1024 * 1024)} МБ — не обработан")
                continue
            data = path.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            if self.ledger.done(sha):
                continue
            archived = self._archive(bank_code, sha, data)
            adapter = ADAPTERS[self.formats.get(bank_code, "canonical")]
            before = mapper.errors
            try:
                parsed = adapter.parse(data, display)
            except BankFileError as exc:
                mapper.report(display, exc.code, str(exc))
                self.ledger.mark(FileEntry(sha, bank_code, display, len(data), "unknown",
                                           "rejected", sink.load_id, 0, 1, archived))
                continue
            staged = mapper.stage(bank_code, display, parsed)
            total += staged
            self.ledger.mark(FileEntry(sha, bank_code, display, len(data), parsed.kind, "staged",
                                       sink.load_id, staged, mapper.errors - before, archived))
            log.info("bank_file_staged", bank=bank_code, file=display, kind=parsed.kind,
                     rows=staged, errors=mapper.errors - before)
        return ExtractStats(total, {})

    # ── Yordamchilar ────────────────────────────────────────────────
    def _candidates(self) -> list[tuple[str, Path]]:
        found: list[tuple[float, str, str, Path]] = []
        for bank_code in sorted(BANKS):
            folder = self.inbox / bank_code
            if not folder.is_dir():
                continue
            for path in folder.glob("*.csv"):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if path.is_file() and self.now() - stat.st_mtime >= self.min_age:
                    found.append((stat.st_mtime, path.name, bank_code, path))
        return [(bank, path) for _, _, bank, path in sorted(found)]

    def _archive(self, bank_code: str, sha: str, data: bytes) -> str:
        folder = self.archive / bank_code / datetime.now(UTC).strftime("%Y-%m")
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{sha}.csv"
        if not target.exists():
            partial = folder / f"{sha}.part"
            partial.write_bytes(data)
            os.chmod(partial, 0o640)
            partial.replace(target)
        return str(target.relative_to(self.archive))
