"""Shifrlangan ustunlar reyestri va kalit rotatsiyasidan keyin qayta shifrlash.

Audit (AUDIT va AUDIT_CHAIN maqsadlari) qayta shifrlanmaydi: jurnal faqat qo'shishga
ochiq va hash-chain shifrmatnni (yoki HMAC kalitini) o'z ichiga oladi. Eski AUDIT/
AUDIT_CHAIN kalitlari saqlash muddati davomida `decrypt_only` holatida qoladi va hech
qachon retire qilinmaydi (`core.mfa_challenges.pending_secret_enc`dan farqli o'laroq,
audit qatorlari yillar davomida qayta tekshirilishi kerak).

`core.mfa_challenges.pending_secret_enc` (Purpose.MFA) qasddan REGISTRY'ga kiritilmagan:
challenge'ning umri atigi 5 daqiqa, `retire-keys`ning standart grace muddati (>= 10 daqiqa)
uni allaqachon qamrab oladi — rotatsiya paytida "hozir kutilayotgan" qiymat bo'lsa ham, u
eski faol kalit bilan shifrlangan bo'lib qoladi va grace muddati ichida tabiiy ravishda
tugaydi/o'chiriladi (`app.cli cleanup`), shuning uchun uni alohida qayta shifrlash ortiqcha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.crypto import Keyring, Purpose


@dataclass(frozen=True, slots=True)
class EncryptedColumn:
    table: str
    pk: str
    column: str
    purpose: Purpose

    def aad(self, pk_value: object) -> str:
        return f"{self.table}.{self.column}:{pk_value}"


REGISTRY: tuple[EncryptedColumn, ...] = (
    EncryptedColumn("core.users", "id", "totp_secret_enc", Purpose.MFA),
    EncryptedColumn("core.sessions", "id", "ip_enc", Purpose.PII),
)
NON_RETIRABLE = frozenset({Purpose.AUDIT, Purpose.AUDIT_CHAIN})
_VERSION_SQL = "(get_byte({col}, 1) * 256 + get_byte({col}, 2))"


def _columns(purpose: Purpose) -> list[EncryptedColumn]:
    return [c for c in REGISTRY if c.purpose == purpose]


def reencrypt(conn: Connection, ring: Keyring, purpose: Purpose, batch: int = 500) -> int:
    active = ring.active[purpose]
    total = 0
    for col in _columns(purpose):
        version = _VERSION_SQL.format(col=col.column)
        # Identifikatorlar faqat REGISTRY'dan olinadi — foydalanuvchi kiritmaydi.
        select_sql = text(
            f"SELECT {col.pk}, {col.column} FROM {col.table} "  # noqa: S608
            f"WHERE {col.column} IS NOT NULL AND {version} <> :v LIMIT :n FOR UPDATE"
        )
        update_sql = text(f"UPDATE {col.table} SET {col.column} = :b WHERE {col.pk} = :pk")  # noqa: S608
        while True:
            rows = conn.execute(select_sql, {"v": active, "n": batch}).all()
            if not rows:
                break
            for pk, blob in rows:
                plain = ring.decrypt(purpose, bytes(blob), col.aad(pk))
                conn.execute(update_sql, {"b": ring.encrypt(purpose, plain, col.aad(pk)), "pk": pk})
            total += len(rows)
    return total


def versions_in_use(conn: Connection, purpose: Purpose) -> set[int]:
    used: set[int] = set()
    for col in _columns(purpose):
        version = _VERSION_SQL.format(col=col.column)
        used |= set(
            conn.execute(
                text(f"SELECT DISTINCT {version} FROM {col.table} WHERE {col.column} IS NOT NULL")  # noqa: S608
            ).scalars()
        )
    return used


def retire_unused(conn: Connection, purpose: Purpose, grace: timedelta) -> list[int]:
    """Ishlatilmayotgan `decrypt_only` versiyalarni yo'q qiladi (o'ralgan kalit o'chiriladi).

    Operator amali — `ugk_migrator` (jadval egasi) sifatida bajariladi: `ugk_app`'ning
    `wrapped_key` ustunini yozish huquqi yo'q (crypto-shredding'dan himoya, spec 3.5), lekin
    bu funksiya `wrapped_key`ni bo'shatadi.

    Faol versiya `grace` dan eski bo'lishi shart: boshqa worker'larning keyring keshi
    (60 s) eski versiya bilan yozib ulgurgan qiymatlar qolmasligi uchun.
    """
    if purpose in NON_RETIRABLE:
        return []
    fresh = conn.execute(
        text(
            "SELECT 1 FROM core.crypto_keys WHERE purpose = :p AND status = 'active' "
            "AND created_at > now() - :g"
        ),
        {"p": purpose.value, "g": grace},
    ).first()
    if fresh is not None:
        return []
    in_use = sorted(versions_in_use(conn, purpose))
    return list(
        conn.execute(
            text(
                "UPDATE core.crypto_keys SET status = 'retired', retired_at = now(), "
                "wrapped_key = '\\x'::bytea "
                "WHERE purpose = :p AND status = 'decrypt_only' AND NOT (version = ANY(:used)) "
                "RETURNING version"
            ),
            {"p": purpose.value, "used": in_use},
        ).scalars()
    )
