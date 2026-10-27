"""Operator CLI: bank hisoblari moslashtirishi (`banks.accounts`) va fayl jurnali.

Hisob raqamlari faylda ochiq keladi, lekin sozlamaga faqat `BA-` kodi va oxirgi 4 raqam
yoziladi; chiqish va xato matnlarida — `…1234` (S2 spec 3.2).
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import text

from app.audit.service import AuditAction, AuditEvent, record
from app.core.config import get_settings
from app.core.db import get_engine
from app.dwh.dates import TASHKENT
from app.dwh.reference import current_setting, validate_setting
from app.etl.banks.accounts import account_code
from app.etl.banks.ledger import DbFileLedger
from app.etl.banks.models import mask, normalize_account
from app.etl.db import etl_transaction

ACCOUNT_COLUMNS = ("account", "bank_code", "branch_code", "currency", "gl_account")
Out = Callable[[str], None]


def read_accounts(path: Path, key: bytes) -> list[dict[str, str]]:
    try:
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{path.name}: faylni o'qib bo'lmadi (UTF-8 CSV kerak)") from exc
    reader = csv.DictReader(io.StringIO(content, newline=""), delimiter=";")
    header = tuple(h.strip().lower() for h in reader.fieldnames or ())
    if header != ACCOUNT_COLUMNS:
        raise ValueError(f"{path.name}: sarlavha «{';'.join(ACCOUNT_COLUMNS)}» bo'lishi kerak")
    out: list[dict[str, str]] = []
    for line, raw in enumerate(reader, start=2):
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError(f"{path.name}:{line}: maydonlar soni noto'g'ri")
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k is not None}
        account = normalize_account(row["account"])
        if not re.fullmatch(r"\d{20}", account):
            raise ValueError(f"{path.name}:{line}: hisob raqami 20 raqamdan iborat bo'lishi kerak")
        out.append({"code": account_code(account, key), "bank_code": row["bank_code"],
                    "branch_code": row["branch_code"], "currency": row["currency"].upper(),
                    "gl_account": row["gl_account"], "last4": account[-4:]})
    return out


def _show(accounts: list[dict[str, str]], out: Out) -> None:
    for a in accounts:
        out(f"{a['code']}  {a['bank_code']:<8} {a['branch_code']:<10} {a['currency']} "
            f"{a['gl_account']}  …{a['last4']}")


def _put(key: str, value: object) -> int:
    with get_engine("app").begin() as conn:
        version = int(conn.execute(text(
            "SELECT coalesce(max(version), 0) FROM core.settings WHERE key = :k"),
            {"k": key}).scalar_one()) + 1
        conn.execute(text("UPDATE core.settings SET is_current = false "
                          "WHERE key = :k AND is_current"), {"k": key})
        conn.execute(text("INSERT INTO core.settings (key, version, value) "
                          "VALUES (:k, :v, CAST(:val AS jsonb))"),
                     {"k": key, "v": version, "val": json.dumps(value, ensure_ascii=False)})
    return version


def bank_accounts_command(file: Path | None, out: Out) -> int:
    if file is None:
        with get_engine("app").connect() as conn:
            current = list(current_setting(conn, "banks.accounts"))
        _show(current, out)
        out(f"banks.accounts: {len(current)} ta hisob")
        return 0
    try:
        value = validate_setting("banks.accounts",
                                 read_accounts(file, get_settings().key_bytes("blind_index_key")))
    except (KeyError, ValueError) as exc:
        out(f"Xato: {mask(str(exc))}")
        return 1
    with etl_transaction() as conn:
        known = set(conn.execute(text("SELECT code FROM dwh.dim_branch")).scalars())
    missing = sorted({a["branch_code"] for a in value} - known)
    if missing:
        out(f"Xato: noma'lum filial kodlari: {', '.join(missing)}")
        return 1
    version = _put("banks.accounts", value)
    record(AuditEvent(action=AuditAction.SETTING_UPDATED, object_type="setting",
                      object_id="banks.accounts",
                      details={"via": "cli", "version": version, "accounts": len(value)}))
    _show(value, out)
    out(f"banks.accounts: versiya {version}, {len(value)} ta hisob")
    return 0


def bank_files_command(limit: int, out: Out) -> int:
    rows = DbFileLedger().recent(limit)
    for r in rows:
        run = r.run_id if r.run_id is not None else "-"
        out(f"{r.first_seen_at.astimezone(TASHKENT):%d.%m.%Y %H:%M}  {r.bank_code:<8} "
            f"{r.status:<9} {r.kind:<9} run={run} строк={r.row_count} ошибок={r.error_count}  "
            f"{r.file_name}")
    out(f"Файлов: {len(rows)}")
    return 0
