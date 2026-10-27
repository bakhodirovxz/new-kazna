"""Admin API sxemalari."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.service import normalize_username

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,64}$")
CODE_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
BranchId = Annotated[int, Field(gt=0, lt=100000)]
PermCode = Annotated[str, Field(max_length=64)]
# I5/minor (fix r1, kengaytirilgan fix r2): taqiqlangan boshqaruv/yashirin-yo'naltirish
# belgilari — ular ko'rinishni buzib ("Иван" ↔ "навИ" aylantirish) ijtimoiy muhandislik uchun
# ishlatilishi mumkin. Diapazonlar BUTUN SONLAR sifatida (chr()/ord() orqali) beriladi —
# satr yoki regex literalida to'g'ridan-to'g'ri unicode kod-nuqta escape yozuvi ishlatish
# manba faylida ko'rinmas belgilarning o'zini qoldirib ketishi mumkin edi (fix r2: aynan shu
# narsa sodir bo'lgan edi — matn uzatish jarayonida escape yozuvi chin belgiga aylanib, fayl
# ichida "yashirin" qolib ketgan edi; endi bu diapazon faqat integer literallardan tuziladi,
# hech qanday noaniqlik yo'q).
_CONTROL_RANGES: tuple[tuple[int, int], ...] = (
    (0x00, 0x1F),  # ASCII boshqaruv belgilari (NUL va h.k.)
    (0x7F, 0x7F),  # DEL
    (0x80, 0x9F),  # C1 boshqaruv belgilari
    (0x202A, 0x202E),  # bidi almashtirish/joylashtirish (LRE/RLE/PDF/LRO/RLO)
    (0x2066, 0x2069),  # bidi izolatlar (LRI/RLI/FSI/PDI)
    (0x2028, 0x2029),  # satr/abzats ajratgichlari
)
_CONTROL_SINGLES: frozenset[int] = frozenset({0x200E, 0x200F, 0x061C})  # LRM, RLM, ALM


def _no_control_chars(value: str) -> str:
    for ch in value:
        code = ord(ch)
        if code in _CONTROL_SINGLES or any(lo <= code <= hi for lo, hi in _CONTROL_RANGES):
            raise ValueError("control characters not allowed")
    return value


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UserCreate(_In):
    # 2FA bor admin data:*:approve bergsa -- joriy TOTP kodi (step-up)
    otp: str | None = Field(default=None, max_length=16)
    username: str = Field(min_length=3, max_length=80)
    full_name: str = Field(min_length=1, max_length=200)
    position_id: int = Field(gt=0)

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        normalized = normalize_username(value)
        if not USERNAME_RE.fullmatch(normalized):
            raise ValueError("username format")
        return normalized

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str) -> str:
        return _no_control_chars(value)


class UserUpdate(_In):
    # 2FA bor admin data:*:approve bergsa -- joriy TOTP kodi (step-up)
    otp: str | None = Field(default=None, max_length=16)
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    position_id: int | None = Field(default=None, gt=0)

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str | None) -> str | None:
        return value if value is None else _no_control_chars(value)


class PositionRef(BaseModel):
    id: int
    code: str
    name: str


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    position: PositionRef
    role_code: str
    is_active: bool
    totp_enabled: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class UserCreated(BaseModel):
    user: UserOut
    temporary_password: str


class TemporaryPassword(BaseModel):
    temporary_password: str


class RoleIn(_In):
    # 2FA bor admin data:*:approve bergsa -- joriy TOTP kodi (step-up)
    otp: str | None = Field(default=None, max_length=16)
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    scope_all: bool
    permissions: list[PermCode] = Field(default_factory=list, max_length=100)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _no_control_chars(value)


class RoleUpdate(_In):
    # 2FA bor admin data:*:approve bergsa -- joriy TOTP kodi (step-up)
    otp: str | None = Field(default=None, max_length=16)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    scope_all: bool | None = None
    permissions: list[PermCode] | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return value if value is None else _no_control_chars(value)


class RoleOut(BaseModel):
    id: int
    code: str
    name: str
    scope_all: bool
    is_system: bool
    permissions: list[str]


class PositionIn(_In):
    # 2FA bor admin data:*:approve bergsa -- joriy TOTP kodi (step-up)
    otp: str | None = Field(default=None, max_length=16)
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    role_id: int = Field(gt=0)
    branch_ids: list[BranchId] = Field(default_factory=list, max_length=100)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _no_control_chars(value)


class PositionUpdate(_In):
    # 2FA bor admin data:*:approve bergsa -- joriy TOTP kodi (step-up)
    otp: str | None = Field(default=None, max_length=16)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role_id: int | None = Field(default=None, gt=0)
    branch_ids: list[BranchId] | None = Field(default=None, max_length=100)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return value if value is None else _no_control_chars(value)


class PositionOut(BaseModel):
    id: int
    code: str
    name: str
    role_id: int
    role_code: str
    is_active: bool
    branch_ids: list[int]


class PermissionOut(BaseModel):
    code: str
    description: str
