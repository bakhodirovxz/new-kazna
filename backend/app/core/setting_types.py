"""Murakkab sozlama qiymatlari modellari va validatorlari (faqat pydantic/stdlib importlari:
`sysconfig` shuni import qiladi, teskari yo'nalish sikl beradi)."""

from __future__ import annotations

import ipaddress
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

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


_BAD_HOSTS = frozenset({"localhost", "metadata.google.internal", "metadata", "instance-data"})


def external_base_url(value: str) -> str:
    """HR API manzili (SSRF himoyasi): loopback, link-local (169.254/16 — bulut metadata),
    0.0.0.0, multicast va sonli/o'n oltilik IP shakllari rad etiladi. RFC1918 (10/8, 172.16/12,
    192.168/16) ruxsat — HR API ichki tarmoqda bo'lishi mumkin. Bo'sh qiymat — o'chirilgan."""
    if not value:
        return value
    host = (urlsplit(value).hostname or "").lower().rstrip(".")
    if not host or host in _BAD_HOSTS or host.endswith((".localhost", ".internal")):
        raise ValueError("hr.base_url: yaroqsiz xost")
    if host.replace(".", "").isdigit() or host.startswith("0x"):
        try:
            ip = ipaddress.IPv4Address(host)
        except ValueError as exc:  # 2130706433, 0x7f.1 va h.k. — yashirin IP shakllari
            raise ValueError("hr.base_url: IP manzil shakli yaroqsiz") from exc
        if (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast
                or ip.is_reserved):
            raise ValueError("hr.base_url: ichki xizmat manzillari taqiqlangan")
    return value
