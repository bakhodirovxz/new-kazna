"""O'zgarmas audit jurnali (spec 3.6).

Har yozuv alohida qisqa tranzaksiyada yoziladi — so'rov rollback bo'lsa ham (masalan,
noto'g'ri parol) hodisa yo'qolmaydi. Zanjir: hash = HMAC-SHA256(chain_key[v], prev_hash ||
canonical_json) — oddiy SHA-256 emas, chunki DB yozish huquqiga ega har kim (masalan,
migrator/superuser) kalitsiz zanjirni qayta hisoblab qayta yoza olmasligi kerak (F1).

Yozish FAQAT ikkita SECURITY DEFINER funksiya orqali: `core.audit_reserve()` navbatdagi
id va joriy zanjir boshini zaxiralaydi (FOR UPDATE qulfi chaqiruvchi tranzaksiya
yakunlanguncha ushlab turiladi — parallel yozuvlar ketma-ketlashadi), `core.audit_append()`
boshni qayta tekshirib (mos kelmasa RAISE) qator qo'shadi va boshni yangilaydi. `ugk_app`/
`ugk_etl`'ning `audit_log`/`audit_head` ustida to'g'ridan-to'g'ri yozish huquqi yo'q (F2).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.core import keystore
from app.core.config import DbRole
from app.core.crypto import CryptoError, Purpose
from app.core.db import get_engine
from app.core.logging import mask
from app.core.request_meta import ClientMeta

GENESIS = bytes(32)
CHAIN_FIELDS = (
    "id", "ts", "user_id", "action", "result", "object_type", "object_id",
    "request_id", "details", "ip_enc", "ua_enc", "chain_key_version",
)
_SELECT = (
    "SELECT id, ts, user_id, action, result, object_type, object_id, request_id, details, "
    "ip_enc, ua_enc, chain_key_version, prev_hash, hash FROM core.audit_log"
)
_MAX_BAD_IDS = 100

AuditResult = Literal["ok", "fail", "denied"]


class AuditAction(StrEnum):
    LOGIN_FAIL = "auth.login.fail"
    PASSWORD_OK = "auth.password.ok"  # noqa: S105 -- audit harakat kodi, parol emas
    LOGIN_OK = "auth.login.ok"
    MFA_FAIL = "auth.mfa.fail"
    MFA_ENROLLED = "auth.mfa.enrolled"
    STEP_UP_FAILED = "auth.step_up.failed"
    MFA_OFFER_DISMISSED = "auth.mfa_offer_dismissed"
    BACKUP_CODE_USED = "auth.mfa.backup_code_used"
    LOGOUT = "auth.logout"
    DATA_EXPORTED = "data.exported"
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
    KEY_RETIRED = "admin.key.retired"
    KEY_REWRAPPED = "admin.key.rewrapped"
    AUDIT_EXPORTED = "audit.exported"
    AUDIT_VERIFIED = "audit.verified"
    ETL_RUN_STARTED = "etl.run.started"
    ETL_RUN_FINISHED = "etl.run.finished"
    ETL_RUN_REQUESTED = "admin.etl.run_requested"
    BUILD_ROLLED_BACK = "admin.build.rolled_back"
    ALERT_RULE_UPDATED = "admin.alert_rule.updated"
    FIN_ASSUMPTIONS_UPDATED = "admin.fin_assumptions.updated"
    SETTING_UPDATED = "admin.setting.updated"
    INTEGRATION_UPDATED = "admin.integration.updated"
    INTEGRATION_CHECK_REQUESTED = "admin.integration.check_requested"
    DATA_BATCH_SAVED = "data.batch.saved"
    DATA_BATCH_SUBMITTED = "data.batch.submitted"
    DATA_BATCH_APPROVED = "data.batch.approved"
    DATA_BATCH_REJECTED = "data.batch.rejected"
    DATA_BATCH_WITHDRAWN = "data.batch.withdrawn"
    DATA_BATCH_PUBLISH_FAILED = "data.batch.publish_failed"
    DATA_IMPORTED = "data.imported"
    DATA_IMPORT_REJECTED = "data.import.rejected"
    DATA_APPROVE_GRANTED = "security.data_approve_granted"
    PARTITIONS_DROPPED = "dwh.partitions.dropped"
    RESTORE_TEST_RECORDED = "ops.restore_test.recorded"
    TELEGRAM_SUMMARY_SENT = "notify.telegram.summary"
    AI_REQUEST = "ai.request"
    AI_JOURNAL_PURGED = "ai.journal.purged"
    RLS_VIOLATION = "security.rls_violation_attempt"
    ACCESS_DENIED = "security.access_denied"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    action: AuditAction
    result: AuditResult = "ok"
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
    bad_ids: list[int]
    first_bad_id: int | None


def ip_aad(audit_id: int) -> str:
    # Global konvensiyaga moslashtirilgan (cheap minor, final review): {schema}.{table}.
    # {column}:{pk} — REENCRYPT_EXEMPT registridagi kalit ("core.audit_log.ip_enc") bilan
    # bir xil ustun nomi.
    return f"core.audit_log.ip_enc:{audit_id}"


def ua_aad(audit_id: int) -> str:
    return f"core.audit_log.ua_enc:{audit_id}"


def _encode(value: Any) -> Any:
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value).hex()
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value


def canonical(row: dict[str, Any] | RowMapping) -> bytes:
    payload = {name: _encode(row[name]) for name in CHAIN_FIELDS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def chain_hash(key: bytes, prev: bytes, row: dict[str, Any] | RowMapping) -> bytes:
    return hmac.new(key, prev + canonical(row), hashlib.sha256).digest()


def _clean_str(value: str) -> str:
    """NUL baytlarni olib tashlaydi va yolg'on surrogate kod nuqtalarini (masalan,
    so'rov tanasidagi buzuq UTF-16 juftlikdan hosil bo'lgan `\\ud800`) almashtiradi (R2-1) —
    ikkalasi ham keyinroq jsonb yozishda yoki UTF-8 kodlashda xato bilan yiqilishga olib keladi."""
    return value.replace("\x00", "").encode("utf-8", "replace").decode("utf-8")


def _sanitize(value: Any) -> Any:
    """`details`ni JSON-xavfsiz primitivlarga aylantiradi (F5/R2-1) — hodisa hech qachon
    yozilmay qolmasligi kerak, hatto yovuz/g'alati kiritilgan qiymatlar (NUL, yolg'on
    surrogatlar, NaN, katta float, Decimal/UUID/datetime va h.k.) bilan ham."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _clean_str(value)
    if isinstance(value, dict):
        return {_clean_str(str(k)): _sanitize(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_sanitize(v) for v in value]
    # Decimal, UUID, datetime, bytes va h.k. — umumiy matn ko'rinishi.
    return _clean_str(str(value))


def _clean_text(value: str | None, max_len: int | None) -> str | None:
    if value is None:
        return None
    cleaned = _clean_str(value)
    return cleaned[:max_len] if max_len is not None else cleaned


def record(event: AuditEvent, *, role: DbRole = "app") -> int:
    details = mask(_sanitize(event.details))
    object_type = _clean_text(event.object_type, 32)
    object_id = _clean_text(event.object_id, 64)
    request_id = _clean_text(event.request_id, 32)
    ip = _clean_text(event.ip, None)
    ua = _clean_text(event.ua, 512)

    # R2-4: keshni tranzaksiyadan TASHQARIDA isitib qo'yamiz — aks holda kesh eskirgan
    # bo'lsa, `core.audit_head`ning FOR UPDATE qulfi ostida turib (audit_reserve() ichida)
    # pool'dan yana bir ulanish so'ralishi mumkin edi (parallel yuklamada tiqilib qolish xavfi).
    keystore.get_keyring()

    with get_engine(role).begin() as conn:
        prev_raw, audit_id_raw = conn.execute(
            text("SELECT prev_hash, new_id FROM core.audit_reserve()")
        ).one()
        prev = bytes(prev_raw)
        audit_id = int(audit_id_raw)
        version, key = keystore.hmac_key(Purpose.AUDIT_CHAIN)
        row: dict[str, Any] = {
            "id": audit_id,
            "ts": datetime.now(UTC),
            "user_id": event.user_id,
            "action": str(event.action),
            "result": event.result,
            "object_type": object_type,
            "object_id": object_id,
            "request_id": request_id,
            "details": details,
            "ip_enc": keystore.encrypt_str(Purpose.AUDIT, ip, ip_aad(audit_id)) if ip else None,
            "ua_enc": keystore.encrypt_str(Purpose.AUDIT, ua, ua_aad(audit_id)) if ua else None,
            "chain_key_version": version,
        }
        digest = chain_hash(key, prev, row)
        conn.execute(
            text(
                "SELECT core.audit_append(:id, :ts, :user_id, :action, :result, "
                ":object_type, :object_id, :request_id, CAST(:details AS jsonb), "
                ":ip_enc, :ua_enc, :chain_key_version, :prev_hash, :hash)"
            ),
            {
                **row,
                "details": json.dumps(details, ensure_ascii=False, allow_nan=False),
                "prev_hash": prev,
                "hash": digest,
            },
        )
    return audit_id


def log_event(
    meta: ClientMeta,
    action: AuditAction,
    *,
    user_id: int | None,
    result: AuditResult = "ok",
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
    """REPEATABLE READ tranzaksiyasi ichida chaqirilishi kerak (verify_chain_snapshot).

    Har bir qator ikki mustaqil tekshiruvdan o'tadi: (1) uning `prev_hash`'i haqiqatda
    oldingi qatorning saqlangan `hash`'iga (yoki `core.audit_anchor`ga — zanjir boshiga)
    teng ekanligi, (2) uning `hash`'i o'z `prev_hash`'i va tarkibidan to'g'ri hisoblanganligi.
    Uzilish topilsa ham, keyingi qatorlar HAQIQIY saqlangan `hash` asosida mustaqil
    tekshirilishda davom etadi — shu orqali bir nechta mustaqil buzilish alohida topiladi (F3).
    """
    head_id, head_hash = conn.execute(
        text("SELECT last_id, last_hash FROM core.audit_head WHERE id = 1")
    ).one()
    anchor_hash = bytes(
        conn.execute(
            text("SELECT last_dropped_hash FROM core.audit_anchor WHERE id = 1")
        ).scalar_one()
    )
    bad_ids: list[int] = []
    prev = anchor_hash
    last_id: int | None = None
    checked = 0
    result = conn.execution_options(stream_results=True, yield_per=1000).execute(
        # nosemgrep: avoid-sqlalchemy-text
        text(f"{_SELECT} ORDER BY id")
    )
    for row in result.mappings():
        row_id = int(row["id"])
        stored_prev = bytes(row["prev_hash"])
        stored_hash = bytes(row["hash"])
        try:
            _, key = keystore.hmac_key(Purpose.AUDIT_CHAIN, int(row["chain_key_version"]))
        except CryptoError:
            # R2-3: noma'lum (masalan, buzilgan yoki hech qachon bo'lmagan) kalit versiyasi
            # butun tekshiruvni to'xtatmasligi kerak — qatorni buzuq deb belgilab, qolgan
            # zanjirni HAQIQIY saqlangan hash asosida mustaqil tekshirishda davom etamiz.
            bad = True
        else:
            expected = chain_hash(key, stored_prev, row)
            bad = stored_prev != prev or expected != stored_hash
        if bad and len(bad_ids) < _MAX_BAD_IDS:
            bad_ids.append(row_id)
        prev, last_id, checked = stored_hash, row_id, checked + 1
    if checked == 0:
        # R2-4: retention hamma qatorni o'chirib yuborgan bo'lishi mumkin — bu holda "ok"
        # faqat anchor haqiqatan ham boshning o'zi bilan mos kelsa (yoki ikkalasi ham
        # genesis'da bo'lsa); aks holda (qatorlar yo'q, lekin bosh boshqa narsaga ishora
        # qilsa) bu xato hisoblanadi.
        head_bad = bytes(head_hash) != anchor_hash
    else:
        head_bad = last_id != head_id or bytes(head_hash) != prev
    if head_bad:
        bad_head_id = head_id if head_id is not None else -1
        if bad_head_id not in bad_ids and len(bad_ids) < _MAX_BAD_IDS:
            bad_ids.append(bad_head_id)
    return ChainReport(
        ok=not bad_ids,
        checked=checked,
        bad_ids=bad_ids,
        first_bad_id=bad_ids[0] if bad_ids else None,
    )


def verify_chain_snapshot() -> ChainReport:
    engine = get_engine("app")
    with (
        engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn,
        conn.begin(),
    ):
        return verify_chain(conn)
