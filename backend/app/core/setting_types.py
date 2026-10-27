"""Murakkab sozlama qiymatlari modellari va validatorlari (faqat pydantic/stdlib importlari:
`sysconfig` shuni import qiladi, teskari yo'nalish sikl beradi)."""

from __future__ import annotations

import re
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


# S3: АСКУЭ stansiyalari ↔ filiallar (`askue.stations`). `code` — kunlik eksport kodi,
# `name` — jonli manba (treplex.uz) nomi; bir filialga bir nechta stansiya bog'lanishi mumkin.
STATION_KINDS: tuple[str, ...] = ("ges", "cascade")
_APOSTROPHES = re.compile(r"[‘’ʻʼ`´]")


def normalize_name(text: str) -> str:
    """Nomlarni solishtirish uchun: apostrof variantlari, bo'shliqlar, registr."""
    return " ".join(_APOSTROPHES.sub("'", text).split()).casefold()


class AskueStation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    code: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,40}$")]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    branch_code: Annotated[str, Field(min_length=1, max_length=32)]


def askue_stations(value: list[AskueStation]) -> list[dict[str, str]]:
    codes = [s.code for s in value]
    names = [normalize_name(s.name) for s in value]
    if len(set(codes)) != len(codes):
        raise ValueError("askue.stations: stansiya kodi takrorlangan")
    if len(set(names)) != len(names) or not all(names):
        raise ValueError("askue.stations: stansiya nomi bo'sh yoki takrorlangan")
    return [s.model_dump() for s in value]
