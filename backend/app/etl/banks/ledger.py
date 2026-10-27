"""Bank fayllari jurnali (core.bank_files): SHA-256 bo'yicha — fayl qayta o'qilmaydi, agar u
rad etilgan (yakuniy) yoki muvaffaqiyatli tugagan ETL yugurishida staging'ga yozilgan bo'lsa.
Muvaffaqiyatsiz yugurishdagi fayl keyingi safar qayta o'qiladi (S2 spec 3.2).
Jurnal yozuvi alohida tranzaksiyada — yugurish natijasidan qat'i nazar saqlanadi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import text

from app.etl.db import etl_transaction


@dataclass(frozen=True, slots=True)
class FileEntry:
    sha256: str
    bank_code: str
    file_name: str  # maskalangan
    size_bytes: int
    kind: str  # statement | orders | unknown
    status: str  # staged | rejected
    run_id: int | None
    row_count: int
    error_count: int
    archive_path: str | None


@dataclass(frozen=True, slots=True)
class LedgerRow:
    first_seen_at: datetime
    bank_code: str
    file_name: str
    kind: str
    status: str
    run_id: int | None
    row_count: int
    error_count: int


class FileLedger(Protocol):
    def done(self, sha256: str) -> bool: ...

    def mark(self, entry: FileEntry) -> None: ...


class DbFileLedger:
    def done(self, sha256: str) -> bool:
        with etl_transaction() as conn:
            row = conn.execute(text(
                "SELECT f.status, r.status AS run_status FROM core.bank_files f "
                "LEFT JOIN core.etl_run r ON r.id = f.run_id WHERE f.sha256 = :h"),
                {"h": sha256}).one_or_none()
        if row is None:
            return False
        return bool(row.status == "rejected" or row.run_status == "success")

    def mark(self, entry: FileEntry) -> None:
        with etl_transaction() as conn:
            conn.execute(text(
                "INSERT INTO core.bank_files (sha256, bank_code, file_name, size_bytes, kind, "
                "status, run_id, row_count, error_count, archive_path) VALUES (:sha, :bank, "
                ":name, :size, :kind, :status, :run, :rows, :errors, :archive) "
                "ON CONFLICT (sha256) DO UPDATE SET kind = EXCLUDED.kind, "
                "status = EXCLUDED.status, run_id = EXCLUDED.run_id, "
                "row_count = EXCLUDED.row_count, error_count = EXCLUDED.error_count, "
                "archive_path = EXCLUDED.archive_path, updated_at = now()"),
                {"sha": entry.sha256, "bank": entry.bank_code, "name": entry.file_name[:255],
                 "size": entry.size_bytes, "kind": entry.kind, "status": entry.status,
                 "run": entry.run_id, "rows": entry.row_count, "errors": entry.error_count,
                 "archive": entry.archive_path})

    def recent(self, limit: int) -> list[LedgerRow]:
        with etl_transaction() as conn:
            rows = conn.execute(text(
                "SELECT first_seen_at, bank_code, file_name, kind, status, run_id, row_count, "
                "error_count FROM core.bank_files ORDER BY first_seen_at DESC LIMIT :n"),
                {"n": max(1, min(limit, 1000))}).all()
        return [LedgerRow(r.first_seen_at, r.bank_code, r.file_name, r.kind, r.status,
                          r.run_id, r.row_count, r.error_count) for r in rows]
