"""O'zgarmas audit jurnali (spec 3.6).

Har yozuv alohida qisqa tranzaksiyada yoziladi — so'rov rollback bo'lsa ham (masalan,
noto'g'ri parol) hodisa yo'qolmaydi. Zanjir: hash = SHA-256(prev_hash || kanonik_json).
Zanjir boshi `core.audit_head` da FOR UPDATE qulfi ostida — parallel yozuvlar ketma-ketlashadi.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import get_engine
from app.core.logging import mask
from app.core.request_meta import ClientMeta

GENESIS = bytes(32)
CHAIN_FIELDS = (
    "id", "ts", "user_id", "action", "result", "object_type", "object_id",
    "request_id", "details", "ip_enc", "ua_enc",
)
_SELECT = (
    "SELECT id, ts, user_id, action, result, object_type, object_id, request_id, details, "
    "ip_enc, ua_enc, prev_hash, hash FROM core.audit_log"
)


class AuditAction(StrEnum):
    LOGIN_FAIL = "auth.login.fail"
    PASSWORD_OK = "auth.password.ok"  # noqa: S105 -- audit harakat kodi, parol emas
    LOGIN_OK = "auth.login.ok"
    MFA_FAIL = "auth.mfa.fail"
    MFA_ENROLLED = "auth.mfa.enrolled"
    BACKUP_CODE_USED = "auth.mfa.backup_code_used"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGED = "auth.password.changed"  # noqa: S105 -- audit harakat kodi, parol emas
    PASSWORD_CHANGE_FAIL = "auth.password.change_fail"  # noqa: S105 -- audit harakat kodi
    SESSION_REVOKED = "auth.session.revoked"
    USER_CREATED = "admin.user.created"
    USER_UPDATED = "admin.user.updated"
    USER_BLOCKED = "admin.user.blocked"
    USER_UNBLOCKED = "admin.user.unblocked"
    USER_PASSWORD_RESET = "admin.user.password_reset"  # noqa: S105 -- audit harakat kodi
    USER_MFA_RESET = "admin.user.mfa_reset"
    ROLE_CREATED = "admin.role.created"
    ROLE_UPDATED = "admin.role.updated"
    POSITION_CREATED = "admin.position.created"
    POSITION_UPDATED = "admin.position.updated"
    KEY_ROTATED = "admin.key.rotated"
    AUDIT_EXPORTED = "audit.exported"
    AUDIT_VERIFIED = "audit.verified"
    RLS_VIOLATION = "security.rls_violation_attempt"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    action: AuditAction
    result: str = "ok"
    user_id: int | None = None
    object_type: str | None = None
    object_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    ip: str | None = None
    ua: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ChainReport:
    ok: bool
    checked: int
    first_bad_id: int | None


def ip_aad(audit_id: int) -> str:
    return f"core.audit_log.ip:{audit_id}"


def ua_aad(audit_id: int) -> str:
    return f"core.audit_log.ua:{audit_id}"


def _encode(value: Any) -> Any:
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value).hex()
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value


def canonical(row: dict[str, Any] | RowMapping) -> bytes:
    payload = {name: _encode(row[name]) for name in CHAIN_FIELDS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def chain_hash(prev: bytes, row: dict[str, Any] | RowMapping) -> bytes:
    return hashlib.sha256(prev + canonical(row)).digest()


def record(event: AuditEvent) -> int:
    details = mask(event.details)
    with get_engine("app").begin() as conn:
        prev = bytes(
            conn.execute(
                text("SELECT last_hash FROM core.audit_head WHERE id = 1 FOR UPDATE")
            ).scalar_one()
        )
        audit_id = int(conn.execute(text("SELECT nextval('core.audit_log_id_seq')")).scalar_one())
        row: dict[str, Any] = {
            "id": audit_id,
            "ts": datetime.now(UTC),
            "user_id": event.user_id,
            "action": str(event.action),
            "result": event.result,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "request_id": event.request_id,
            "details": details,
            "ip_enc": (
                keystore.encrypt_str(Purpose.AUDIT, event.ip, ip_aad(audit_id))
                if event.ip
                else None
            ),
            "ua_enc": (
                keystore.encrypt_str(Purpose.AUDIT, event.ua[:512], ua_aad(audit_id))
                if event.ua
                else None
            ),
        }
        digest = chain_hash(prev, row)
        conn.execute(
            text(
                "INSERT INTO core.audit_log (id, ts, user_id, action, result, object_type, "
                "object_id, request_id, details, ip_enc, ua_enc, prev_hash, hash) VALUES "
                "(:id, :ts, :user_id, :action, :result, :object_type, :object_id, :request_id, "
                "CAST(:details AS jsonb), :ip_enc, :ua_enc, :prev_hash, :hash)"
            ),
            {**row, "details": json.dumps(details, ensure_ascii=False), "prev_hash": prev,
             "hash": digest},
        )
        conn.execute(
            text("UPDATE core.audit_head SET last_id = :id, last_hash = :h WHERE id = 1"),
            {"id": audit_id, "h": digest},
        )
    return audit_id


def log_event(
    meta: ClientMeta,
    action: AuditAction,
    *,
    user_id: int | None,
    result: str = "ok",
    object_type: str | None = None,
    object_id: object | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    return record(
        AuditEvent(
            action=action,
            result=result,
            user_id=user_id,
            object_type=object_type,
            object_id=None if object_id is None else str(object_id),
            details=details or {},
            ip=meta.ip,
            ua=meta.ua,
            request_id=meta.request_id,
        )
    )


def verify_chain(conn: Connection) -> ChainReport:
    """REPEATABLE READ tranzaksiyasi ichida chaqirilishi kerak (verify_chain_snapshot)."""
    head_id, head_hash = conn.execute(
        text("SELECT last_id, last_hash FROM core.audit_head WHERE id = 1")
    ).one()
    prev: bytes | None = None
    last_id: int | None = None
    checked = 0
    result = conn.execution_options(stream_results=True, yield_per=1000).execute(
        text(f"{_SELECT} ORDER BY id")
    )
    for row in result.mappings():
        stored_prev = bytes(row["prev_hash"])
        if prev is not None and stored_prev != prev:
            return ChainReport(False, checked, row["id"])
        expected = chain_hash(stored_prev, row)
        if expected != bytes(row["hash"]):
            return ChainReport(False, checked, row["id"])
        prev, last_id, checked = expected, row["id"], checked + 1
    if head_id != last_id or (prev is not None and bytes(head_hash) != prev):
        return ChainReport(False, checked, head_id)
    return ChainReport(True, checked, None)


def verify_chain_snapshot() -> ChainReport:
    engine = get_engine("app")
    with (
        engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn,
        conn.begin(),
    ):
        return verify_chain(conn)
