"""Murakkab sozlama qiymatlari modellari va validatorlari (faqat pydantic/stdlib importlari:
`sysconfig` shuni import qiladi, teskari yo'nalish sikl beradi)."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

CALENDAR_KINDS = ("taxes", "salary", "loans")  # qolgan statyalar — "contracts"


def calendar_kinds(value: dict[str, list[str]]) -> dict[str, list[str]]:
    unknown = set(value) - set(CALENDAR_KINDS)
    if unknown:
        raise ValueError(f"noma'lum kalendar turi: {sorted(unknown)}")
    seen: set[str] = set()
    for codes in value.values():
        for code in codes:
            if not code or len(code) > 32 or code in seen:
                raise ValueError(f"noto'g'ri yoki takrorlangan statya kodi: {code!r}")
            seen.add(code)
    return {kind: list(codes) for kind, codes in value.items()}


_BLOCKED_NAMES = frozenset({"localhost", "db", "redis", "api", "caddy", "worker", "backup",
                            "migrate", "metadata.google.internal"})


def onec_url_host(url: str) -> str:
    """Manzil xosti: SSRF'ga qarshi loopback/link-local/metadata va compose xizmat nomlari rad
    etiladi; RFC1918 (1C ichki tarmoqda) ruxsat."""
    if not url:
        return url
    import ipaddress
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host in _BLOCKED_NAMES or host.endswith(".localhost"):
            raise ValueError("onec.base_url: xost taqiqlangan") from None
        return url
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        raise ValueError("onec.base_url: xost taqiqlangan")
    return url


class OneCOrg(BaseModel):
    """1C tashkiloti ↔ filial (spec 3.1). org_uid — 1C UID (so'rovda `org_uid`)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    branch_code: Annotated[str, Field(min_length=1, max_length=32)]
    org_uid: Annotated[str, Field(pattern=r"^[0-9A-Za-z-]{1,64}$")]
    org_name: Annotated[str, Field(min_length=1, max_length=300)]


def onec_orgs(value: list[OneCOrg]) -> list[dict[str, str]]:
    for attr in ("branch_code", "org_uid", "org_name"):
        values = [getattr(org, attr) for org in value]
        if len(set(values)) != len(values):
            raise ValueError(f"onec.orgs: {attr} takrorlangan")
    return [org.model_dump() for org in value]


# --- S2: banklar (TZ 8 «Банки»). Katalog nomi = bank kodi: /data/import/banks/<kod>/.
BANKS: dict[str, str] = {
    "sqb": "Узпромстройбанк",
    "nbu": "Национальный банк",
    "asaka": "Асакабанк",
    "ipoteka": "Ипотека-банк",
    "xalq": "Халк банк",
}
ADAPTER_NAMES: tuple[str, ...] = ("canonical",)
ACCOUNT_CODE_PATTERN = r"^BA-[0-9a-f]{16}$"


def _known_bank(code: str) -> str:
    if code not in BANKS:
        raise ValueError(f"noma'lum bank kodi: {code!r}")
    return code


class BankAccount(BaseModel):
    """Hisob <-> (bank, filial, valyuta, 1C schyoti) moslashtirishi (`banks.accounts`).
    Hisob raqami saqlanmaydi — faqat `BA-<HMAC[:16]>` kodi va oxirgi 4 raqam."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    code: Annotated[str, Field(pattern=ACCOUNT_CODE_PATTERN)]
    bank_code: Annotated[str, AfterValidator(_known_bank)]
    branch_code: Annotated[str, Field(min_length=1, max_length=32)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    gl_account: Annotated[str, Field(pattern=r"^\d{4}$")]
    last4: Annotated[str, Field(pattern=r"^\d{4}$")]


def bank_accounts(value: list[BankAccount]) -> list[dict[str, str]]:
    codes = [a.code for a in value]
    if len(set(codes)) != len(codes):
        raise ValueError("banks.accounts: hisob kodi takrorlangan")
    return [a.model_dump() for a in value]


def branch_codes(value: list[str]) -> list[str]:
    if len(set(value)) != len(value) or any(not c or len(c) > 32 for c in value):
        raise ValueError("filial kodlari bo'sh, uzun yoki takrorlangan")
    return list(value)


def bank_formats(value: dict[str, str]) -> dict[str, str]:
    unknown = set(value) - set(BANKS)
    if unknown:
        raise ValueError(f"noma'lum bank: {sorted(unknown)}")
    bad = sorted({v for v in value.values() if v not in ADAPTER_NAMES})
    if bad:
        raise ValueError(f"noma'lum format adapteri: {bad}")
    return dict(value)


def currencies(value: list[str]) -> list[str]:
    if not value or len(set(value)) != len(value) or "UZS" in value \
            or any(not re.fullmatch(r"[A-Z]{3}", c) for c in value):
        raise ValueError("fx.currencies: ISO 4217 kodlari (UZS emas), takrorsiz")
    return list(value)


# S4: xarid usullari va normativ kunlar (app.etl.zakupki.codes shundan re-export qiladi).
METHODS: tuple[str, ...] = ("eshop", "contest", "tender", "exchange", "direct", "other")
# Vaqtinchalik normativlar (prototip PMETH yuqori chegarasi) — mijoz tasdiqlaydi (spec 12, 2-savol).
DEFAULT_METHOD_NORMS: dict[str, int] = {
    "eshop": 15, "contest": 40, "tender": 70, "exchange": 20, "direct": 12, "other": 40,
}


def method_norms(value: dict[str, int]) -> dict[str, int]:
    if set(value) != set(METHODS):
        raise ValueError("zakupki.method_norms: barcha usullar uchun normativ kerak")
    return dict(value)


def normalize_org(name: str) -> str:
    """Tashkilot nomini solishtirish uchun: apostrof variantlari, bo'shliqlar, registr."""
    for ch in "ʻʼ‘’`":
        name = name.replace(ch, "'")
    return " ".join(name.casefold().split())


class HrOrg(BaseModel):
    """HR manbasidagi tashkilot ↔ filial (`hr.orgs`)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    org: Annotated[str, Field(min_length=1, max_length=200)]
    branch_code: Annotated[str, Field(min_length=1, max_length=32)]


def hr_orgs(value: list[HrOrg]) -> list[dict[str, str]]:
    names = [normalize_org(o.org) for o in value]
    if not all(names) or len(set(names)) != len(names):
        raise ValueError("hr.orgs: tashkilot nomi bo'sh yoki takrorlangan")
    return [o.model_dump() for o in value]
