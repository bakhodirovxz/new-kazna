"""Murakkab sozlama qiymatlari modellari va validatorlari (faqat pydantic/stdlib importlari:
`sysconfig` shuni import qiladi, teskari yo'nalish sikl beradi)."""

from __future__ import annotations

from typing import Annotated

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
