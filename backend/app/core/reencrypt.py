"""Shifrlangan ustunlar reyestri va kalit rotatsiyasidan keyin qayta shifrlash.

Audit (AUDIT va AUDIT_CHAIN maqsadlari) qayta shifrlanmaydi: jurnal faqat qo'shishga
ochiq va hash-chain shifrmatnni (yoki HMAC kalitini) o'z ichiga oladi. Eski AUDIT/
AUDIT_CHAIN kalitlari saqlash muddati davomida `decrypt_only` holatida qoladi va hech
qachon retire qilinmaydi (`core.mfa_challenges.pending_secret_enc`dan farqli o'laroq,
audit qatorlari yillar davomida qayta tekshirilishi kerak).

`REGISTRY`/`REENCRYPT_EXEMPT` to'liqligi `tests/test_reencrypt_registry.py`da sxema
introspeksiyasi bilan tekshiriladi (I1): core/stg/dwh/mart sxemalaridagi har bir `*_enc`
nomli `bytea` ustun ikkalasining birida bo'lishi SHART — aks holda kalit retire
qilinganda o'sha ustun sukut bo'yicha qayta shifrlanmay, "jimgina" o'qib bo'lmaydigan
holga kelishi mumkin edi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core import keystore
from app.core.crypto import Keyring, Purpose
from app.core.logging import get_logger

log = get_logger("ugekazna.reencrypt")

MIN_RETIRE_GRACE = timedelta(minutes=10)

# Fix r2 (cheap): faqat shifrlangan ustunlarni qayta shifrlaydigan ikkita ulanish bor —
# `app.core.config.DbRole`ning uchinchi qiymati ("etl") bu yerda hech qachon uchramaydi
# (ETL shifrlangan ustunlarni qayta shifrlamaydi, faqat yozadi/o'qiydi), shuning uchun
# kengroq `DbRole`dan foydalanish o'rniga shu ikkitasiga qattiq toraytirilgan.
EncryptedColumnRole = Literal["app", "migrator"]


@dataclass(frozen=True, slots=True)
class EncryptedColumn:
    table: str
    pk: str
    column: str
    purpose: Purpose
    # Fix r1 (I1): qaysi DB ulanishi bu ustunni qayta shifrlashi MUMKIN — `ugk_app`da
    # `dwh.*` shifrlangan rekvizitlarga o'qish/yozish huquqi yo'q (I1 fix r1), shuning
    # uchun ular faqat "migrator" ulanishida (operator CLI, `migrate` konteyneri)
    # qayta shifrlanadi. `core.*` ustunlar an'anaviy — "app" ulanishida (admin API).
    role: EncryptedColumnRole

    def aad(self, pk_value: object) -> str:
        return f"{self.table}.{self.column}:{pk_value}"


REGISTRY: tuple[EncryptedColumn, ...] = (
    EncryptedColumn("core.users", "id", "totp_secret_enc", Purpose.MFA, "app"),
    EncryptedColumn("core.sessions", "id", "ip_enc", Purpose.PII, "app"),
    # Витрина: AAD tabiiy kalit (code) bo'yicha — ETL shifrlaganda surrogat id hali noma'lum.
    # role="migrator": ugk_app'ning bu ustunlarga hech qanday huquqi yo'q (I1 fix r1) —
    # qayta shifrlash faqat `python -m app.cli rotate-key` (migrator ulanishi, `migrate`
    # konteyneri) orqali bajariladi.
    EncryptedColumn("dwh.dim_counterparty", "code", "inn_enc", Purpose.PII, "migrator"),
    EncryptedColumn("dwh.dim_bank", "code", "account_enc", Purpose.BANK, "migrator"),
    # 04b: integratsiya sirlari — admin API (ugk_app) yozadi, AAD tabiiy kalit (name) bo'yicha.
    EncryptedColumn("core.integration_credentials", "name", "value_enc", Purpose.INTEGRATION,
                    "app"),
)
# I1: `REGISTRY`da YO'Q, lekin sxemada mavjud har bir `*_enc` ustun shu yerda ANIQ sababi
# bilan ro'yxatga olinishi SHART (kalit `schema.table.column` formatida) — aks holda
# to'liqlik testi (`test_reencrypt_registry.py`) yiqiladi. Bo'sh REGISTRY'ga ega maqsadlar
# (`retire_unused` refuses purposes with no REGISTRY columns) bilan chalkashtirmaslik kerak:
# bu yerdagi ustunlar ATAYLAB hech qachon qayta shifrlanmaydi (sababi ko'rsatilgan), pastdagi
# esa hali umuman REGISTRY qilinmagan (kelajakdagi reja ularni ro'yxatga oladi).
REENCRYPT_EXEMPT: dict[str, str] = {
    "core.audit_log.ip_enc": (
        "Purpose.AUDIT — NON_RETIRABLE, audit yozuvlari umrbod saqlanadi va hech qachon "
        "qayta shifrlanmaydi (jurnal faqat qo'shishga ochiq)."
    ),
    "core.audit_log.ua_enc": (
        "Purpose.AUDIT — NON_RETIRABLE, audit yozuvlari umrbod saqlanadi va hech qachon "
        "qayta shifrlanmaydi (jurnal faqat qo'shishga ochiq)."
    ),
    "core.mfa_challenges.pending_secret_enc": (
        "Purpose.MFA — challenge umri atigi 5 daqiqa, retire grace (>=10 daqiqa) muddati "
        "ichida tabiiy tugaydi/o'chiriladi (`app.cli cleanup`), shuning uchun qayta "
        "shifrlash ortiqcha."
    ),
}
NON_RETIRABLE = frozenset({Purpose.AUDIT, Purpose.AUDIT_CHAIN})
_VERSION_SQL = "(get_byte({col}, 1) * 256 + get_byte({col}, 2))"


def _columns(
    purpose: Purpose, role: EncryptedColumnRole | None = None
) -> list[EncryptedColumn]:
    return [c for c in REGISTRY if c.purpose == purpose and (role is None or c.role == role)]


def reencrypt(
    conn: Connection,
    ring: Keyring,
    purpose: Purpose,
    *,
    role: EncryptedColumnRole,
    batch: int = 500,
) -> int:
    """Faqat `role` ulanishi yoza oladigan ustunlarni qayta shifrlaydi (I1 fix r1).

    `ugk_app` ulanishida `role="app"` bilan chaqirilsa, `dwh.*` (role="migrator") ustunlar
    tegilmaydi — ular eski versiyada qolaveradi, toki operator CLI migrator ulanishida
    o'zi qayta shifrlamaguncha. Bu ataylab shunday: `versions_in_use` (pastda) BARCHA
    rollardagi ustunlarni skanerlaydi, shuning uchun `retire_unused` eski versiyani hali
    role="migrator" ustun ishlatayotgan bo'lsa yo'q qilmaydi.
    """
    active = ring.active[purpose]
    total = 0
    for col in _columns(purpose, role):
        version = _VERSION_SQL.format(col=col.column)
        # Identifikatorlar faqat REGISTRY'dan olinadi — foydalanuvchi kiritmaydi.
        # nosemgrep: avoid-sqlalchemy-text
        select_sql = text(
            f"SELECT {col.pk}, {col.column} FROM {col.table} "  # noqa: S608
            f"WHERE {col.column} IS NOT NULL AND {version} <> :v LIMIT :n FOR UPDATE"
        )
        # nosemgrep: avoid-sqlalchemy-text
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
                # nosemgrep: avoid-sqlalchemy-text
                text(f"SELECT DISTINCT {version} FROM {col.table} WHERE {col.column} IS NOT NULL")  # noqa: S608
            ).scalars()
        )
    return used


def retire_unused(
    conn: Connection, purpose: Purpose, grace: timedelta, *, allow_short_grace: bool = False
) -> list[int]:
    """Ishlatilmayotgan `decrypt_only` versiyalarni yo'q qiladi (o'ralgan kalit o'chiriladi).

    Operator amali — `ugk_migrator` (jadval egasi) sifatida bajariladi: `ugk_app`'ning
    `wrapped_key` ustunini yozish huquqi yo'q (crypto-shredding'dan himoya, spec 3.5), lekin
    bu funksiya `wrapped_key`ni bo'shatadi.

    Faol versiya `grace` dan eski bo'lishi shart: boshqa worker'larning keyring keshi
    (60 s) eski versiya bilan yozib ulgurgan qiymatlar qolmasligi uchun. `grace` odatda
    `MIN_RETIRE_GRACE` (10 daqiqa)dan kam bo'lishi mumkin emas — bu operator xatosidan
    himoya (juda qisqa grace boshqa worker'larning keshini "quvib o'tib", hali eski
    versiya bilan yozilayotgan qiymatlarni o'qib bo'lmaydigan holga keltirishi mumkin);
    faqat testlar `allow_short_grace=True` bilan bu tekshiruvni ongli bosib o'tadi.

    `purpose`da hech qanday REGISTRY ustuni bo'lmasa (I1: masalan, INTEGRATION —
    hali qayta shifrlash uchun ro'yxatga olinmagan), funksiya RAD ETADI: bo'sh ro'yxat
    qaytaradi va ogohlantirish yozadi — aks holda shu maqsaddagi eski kalitlar, ularga
    tegishli ustunlar hali REGISTRY qilinmagani uchun HECH QACHON qayta shifrlanmasdan
    turib yo'q qilinib, kelajakda o'sha ustunlar ro'yxatga olinganda allaqachon o'qib
    bo'lmaydigan holga kelishi mumkin edi.
    """
    keystore.take_key_lock(conn)
    if not allow_short_grace and grace < MIN_RETIRE_GRACE:
        raise ValueError(
            "grace >= 10 daqiqa bo'lishi kerak "
            "(faqat testlar allow_short_grace=True bilan bosib o'tadi)"
        )
    if purpose in NON_RETIRABLE:
        return []
    if not _columns(purpose):
        log.warning("retire_refused_no_registry_columns", purpose=purpose.value)
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
