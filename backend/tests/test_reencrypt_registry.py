"""I1 (fix round 1): `REGISTRY`/`REENCRYPT_EXEMPT` sxemadagi barcha `*_enc` `bytea`
ustunlarni birgalikda to'liq qamrab olishini tekshiradi.

Nega muhim: agar biror `*_enc` ustun ikkalasida ham bo'lmasa, u ustunga tegishli maqsad
(`Purpose`) kalit rotatsiyasidan keyin `retire_unused` bilan yo'q qilinganda, o'sha ustun
sukut bo'yicha HECH QACHON qayta shifrlanmagan holda qolib, keyinroq (eski kalit
o'chirilgach) umuman o'qib bo'lmaydigan holga kelishi mumkin — bu qaytarib bo'lmaydigan
ma'lumot yo'qotish. Bu test yangi `*_enc` ustun qo'shilganda uni ONGLI ravishda
`REGISTRY`ga (qayta shifrlanadi) yoki `REENCRYPT_EXEMPT`ga (sababi bilan, ataylab
qayta shifrlanmaydi) qo'shishni talab qiladi.
"""

from __future__ import annotations

from sqlalchemy import text

from app.core.db import get_engine
from app.core.reencrypt import REENCRYPT_EXEMPT, REGISTRY

# `ugk_migrator` sxemalarning egasi (barcha migratsiyalar shu rol bilan bajariladi) —
# shuning uchun introspeksiya to'liq ko'rinishni ta'minlash uchun shu ulanishda ishlaydi
# (masalan, `ugk_app`ning `stg`/`dwh`/`mart`ga USAGE huquqi yo'q va ular hozircha bo'sh
# bo'lsa ham, kelajakda jadval qo'shilganda bu test "ko'r" bo'lib qolmasligi kerak).
_SCHEMAS = ("core", "stg", "dwh", "mart")


def _enc_columns() -> list[str]:
    """`pg_catalog` orqali — `information_schema.columns` emas: `core.audit_log` kabi
    RANGE-partition qilingan jadvallarning har bir OY partitsiyasi (masalan,
    `audit_log_202609`) alohida "jadval" sifatida ko'rinib, mantiqan bitta bo'lgan
    `core.audit_log.ip_enc`ni o'nlab nusxaga "ko'paytirib" yuborardi. `NOT relispartition`
    faqat MANTIQIY (ota) jadval/partitsiyalangan jadvalni qoldiradi."""
    with get_engine("migrator").connect() as conn:
        rows = conn.execute(
            text(
                "SELECT n.nspname, c.relname, a.attname "
                "FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_type t ON t.oid = a.atttypid "
                "WHERE n.nspname = ANY(:schemas) AND c.relkind IN ('r', 'p') "
                "AND NOT c.relispartition AND a.attnum > 0 AND NOT a.attisdropped "
                "AND t.typname = 'bytea' AND a.attname ~ '_enc$' "
                "ORDER BY 1, 2, 3"
            ),
            {"schemas": list(_SCHEMAS)},
        ).all()
    return [f"{schema}.{table}.{column}" for schema, table, column in rows]


def test_registry_and_exempt_cover_all_enc_columns() -> None:
    registered = {f"{c.table}.{c.column}" for c in REGISTRY}
    missing = [
        full for full in _enc_columns() if full not in registered and full not in REENCRYPT_EXEMPT
    ]
    assert not missing, f"REGISTRY/REENCRYPT_EXEMPT'da yo'q *_enc ustun(lar): {missing}"


def test_at_least_the_known_columns_are_found() -> None:
    """Introspeksiya so'rovi haqiqatan ham ustunlarni topayotganini tasdiqlaydi — aks holda
    yuqoridagi test noto'g'ri sabab bilan (masalan, bo'sh natija) "o'tib ketishi" mumkin edi."""
    found = set(_enc_columns())
    assert {"core.users.totp_secret_enc", "core.sessions.ip_enc"} <= found
    assert {"core.audit_log.ip_enc", "core.audit_log.ua_enc"} <= found


def test_exempt_reasons_are_documented() -> None:
    assert set(REENCRYPT_EXEMPT) == {
        "core.audit_log.ip_enc",
        "core.audit_log.ua_enc",
        "core.mfa_challenges.pending_secret_enc",
    }
    assert all(reason.strip() for reason in REENCRYPT_EXEMPT.values())
