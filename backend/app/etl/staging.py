"""StagingSink: konnektor qatorlarini stg.rows ga yozadi.

Sezgir maydonlar (INN, hisob raqami) staging'ga yozilishidan OLDIN shifrlanadi — ochiq qiymat
bazaga hech qachon tushmaydi. AAD = "dwh.{jadval}.{ustun}:{code}" (REGISTRY bilan bir xil).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import blind_index
from app.dwh.targets import TARGETS, Target

_INSERT = text("INSERT INTO stg.rows (load_id, target, payload) VALUES (:l, :t, CAST(:p AS jsonb))")


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    raise TypeError(f"JSON'ga aylantirib bo'lmaydi: {type(value).__name__}")


def protect(target: Target, payload: dict[str, Any]) -> dict[str, Any]:
    if not target.sensitive:
        return payload
    code = str(payload.get("code") or "")
    if not code:
        raise ValueError(f"{target.name}: shifrlanadigan qator uchun 'code' majburiy")
    index_key = get_settings().key_bytes("blind_index_key")
    for spec in target.sensitive:
        value = payload.pop(spec.field, None)
        if value is None or str(value).strip() == "":
            payload[spec.enc_column] = None
            payload[spec.bidx_column] = None
            continue
        plain = str(value)
        aad = f"dwh.{target.name}.{spec.enc_column}:{code}"
        payload[spec.enc_column] = "\\x" + keystore.encrypt_str(spec.purpose, plain, aad).hex()
        payload[spec.bidx_column] = "\\x" + blind_index(index_key, spec.index_label, plain).hex()
    return payload


def clear_load(conn: Connection, load_id: int) -> None:
    conn.execute(text("DELETE FROM stg.rows WHERE load_id = :l"), {"l": load_id})
    conn.execute(text("DELETE FROM stg.batch WHERE load_id = :l"), {"l": load_id})


class BufferingSink:
    """Xotirada yig'adi (DB tranzaksiyasiz); `replay` qatorlarni haqiqiy sink'ka o'tkazadi.
    Tarmoq konnektorlari uchun (`buffered = True`): HTTP paytida tranzaksiya ochiq turmaydi."""

    def __init__(self) -> None:
        self._rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self._rows.append((target, dict(row)))

    def replay(self, sink: Any) -> None:
        for target, row in self._rows:
            sink.add(target, row)


class DbStagingSink:
    def __init__(self, conn: Connection, load_id: int, source: str, *,
                 batch_size: int = 2000) -> None:
        self.conn = conn
        self.load_id = load_id
        self.source = source
        self.batch_size = batch_size
        self.counts: Counter[str] = Counter()
        self._buffer: list[dict[str, Any]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        spec = TARGETS.get(target)
        if spec is None:
            raise ValueError(f"noma'lum staging maqsadi: {target}")
        # Fix r1, I1: whitelist tashqarisidagi kalit rad etiladi — XABARDA FAQAT KALIT NOMI,
        # qiymat emas (log/xabarga sezgir ma'lumot chiqib ketmasligi uchun).
        extra = set(row.keys()) - spec.allowed_keys
        if extra:
            raise ValueError(f"{target}: noma'lum maydon(lar): {', '.join(sorted(extra))}")
        payload = protect(spec, dict(row))
        self._buffer.append({
            "l": self.load_id,
            "t": target,
            "p": json.dumps(payload, default=_json_default, ensure_ascii=False),
        })
        self.counts[target] += 1
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if self._buffer:
            self.conn.execute(_INSERT, self._buffer)
            self._buffer = []

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None:
        """Konnektor darajasidagi xato (masalan, bank faylidagi buzilgan qator) — step "extract".
        Chaqiruvchi xabarda maxfiy qiymat (hisob raqami) bo'lmasligini ta'minlaydi."""
        self.conn.execute(
            text("INSERT INTO core.etl_error (run_id, step, severity, target, src_id, code, "
                 "message) VALUES (:r, 'extract', :sev, :t, :s, :c, :m)"),
            {"r": self.load_id, "sev": severity, "t": target[:64],
             "s": None if src_id is None else src_id[:128], "c": code[:32], "m": message[:500]},
        )

    def close(self) -> dict[str, int]:
        self.flush()
        for target, count in self.counts.items():
            self.conn.execute(
                text("INSERT INTO stg.batch (load_id, target, source, row_count) "
                     "VALUES (:l, :t, :s, :n)"),
                {"l": self.load_id, "t": target, "s": self.source, "n": count},
            )
        return dict(self.counts)
