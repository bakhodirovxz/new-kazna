"""Bo'limlar, ruxsatlar va tizim rollari (spec 3.3, TZ 1-bo'lim).

Kod — ruxsatlar ro'yxatining yagona manbai. Tizim rollari faqat BIRINCHI marta
yaratilganda seed qilinadi, keyin ularni administrator boshqaradi.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Section(StrEnum):
    OBZOR = "obzor"
    KAZNA = "kazna"
    KREDITY = "kredity"
    FINMODEL = "finmodel"
    ZAKUPKI = "zakupki"
    SKLAD = "sklad"
    PROIZVODSTVO = "proizvodstvo"
    INVESTICII = "investicii"
    KADRY = "kadry"


SECTION_TITLES: dict[Section, str] = {
    Section.OBZOR: "Обзор",
    Section.KAZNA: "Казначейство",
    Section.KREDITY: "Кредиты",
    Section.FINMODEL: "Финмодель",
    Section.ZAKUPKI: "Закупки",
    Section.SKLAD: "Склад",
    Section.PROIZVODSTVO: "Производство",
    Section.INVESTICII: "Инвестиции",
    Section.KADRY: "Кадры",
}


def section_perm(section: Section) -> str:
    return f"section:{section.value}:view"


class Perm(StrEnum):
    EXPORT_CSV = "export:csv"
    EXPORT_XLSX = "export:xlsx"
    ADMIN_USERS = "admin:users"
    ADMIN_ROLES = "admin:roles"
    ADMIN_SETTINGS = "admin:settings"
    ADMIN_ETL = "admin:etl"
    ADMIN_KEYS = "admin:keys"
    ADMIN_SECURITY = "admin:security"
    ADMIN_INTEGRATIONS = "admin:integrations"
    AUDIT_READ = "audit:read"


_PERM_TITLES: dict[Perm, str] = {
    Perm.EXPORT_CSV: "Выгрузка таблиц в CSV",
    Perm.EXPORT_XLSX: "Выгрузка в Excel (.xlsx)",
    Perm.ADMIN_USERS: "Администрирование: пользователи",
    Perm.ADMIN_ROLES: "Администрирование: должности и роли",
    Perm.ADMIN_SETTINGS: "Администрирование: настройки и пороги",
    Perm.ADMIN_ETL: "Администрирование: загрузки данных",
    Perm.ADMIN_KEYS: "Администрирование: ключи шифрования",
    Perm.ADMIN_SECURITY: "Администрирование: политика безопасности",
    Perm.ADMIN_INTEGRATIONS: "Администрирование: интеграции и учётные данные",
    Perm.AUDIT_READ: "Просмотр журнала аудита",
}

# «Ввод данных»: ruxsatlar Perm enum'iga KIRMAYDI -- admin roli ularni avtomatik olmaydi
# (vazifalar ajratilishi: admin foydalanuvchilarni boshqaradi, moliyaviy ma'lumot kiritmaydi).
DATA_SECTIONS: tuple[Section, ...] = (
    Section.KAZNA, Section.KREDITY, Section.PROIZVODSTVO, Section.INVESTICII, Section.KADRY,
)
DataAction = Literal["write", "approve"]
_DATA_ACTION_TITLES: dict[str, str] = {"write": "ввод и изменение", "approve": "согласование"}


def data_perm(section: Section, action: DataAction) -> str:
    return f"data:{section.value}:{action}"


ALL_DATA_PERMS: tuple[str, ...] = tuple(
    data_perm(s, a) for s in DATA_SECTIONS for a in ("write", "approve")
)

def sod_conflict(perms: Iterable[str]) -> bool:
    """Vazifalar ajratilishi: bitta rolda `admin:*` va `data:*` birga bo'lmaydi."""
    held = set(perms)
    return any(p.startswith("admin:") for p in held) and bool(held & set(ALL_DATA_PERMS))


PERMISSIONS: dict[str, str] = {
    **{section_perm(s): f"Раздел «{t}»: просмотр" for s, t in SECTION_TITLES.items()},
    **{p.value: t for p, t in _PERM_TITLES.items()},
    **{
        data_perm(s, a): f"Ввод данных «{SECTION_TITLES[s]}»: {_DATA_ACTION_TITLES[a]}"
        for s in DATA_SECTIONS
        for a in ("write", "approve")
    },
}


@dataclass(frozen=True, slots=True)
class RoleSeed:
    code: str
    name: str
    scope_all: bool
    permissions: frozenset[str]


def _sections(*items: Section) -> frozenset[str]:
    return frozenset(section_perm(s) for s in items)


_ALL_SECTIONS = _sections(*Section)
def _data(action: DataAction, *items: Section) -> frozenset[str]:
    return frozenset(data_perm(s, action) for s in items)


_EXPORT = frozenset({Perm.EXPORT_CSV.value, Perm.EXPORT_XLSX.value})

ADMIN_ROLE = "admin"
ADMIN_GUARANTEED = frozenset({Perm.ADMIN_USERS.value, Perm.ADMIN_ROLES.value})

ROLE_SEEDS: tuple[RoleSeed, ...] = (
    RoleSeed("rukovodstvo", "Руководство", True, _ALL_SECTIONS | _EXPORT),
    RoleSeed(
        "nach_otdela",
        "Начальник отдела финансирования и контроля денежных потоков",
        True,
        _ALL_SECTIONS | _EXPORT | _data("approve", *DATA_SECTIONS),
    ),
    RoleSeed(
        "spec_kazna",
        "Специалист казначейства",
        True,
        _sections(Section.OBZOR, Section.KAZNA, Section.KREDITY, Section.FINMODEL)
        | _EXPORT
        | _data("write", Section.KAZNA, Section.KREDITY),
    ),
    RoleSeed(
        "economist_filiala",
        "Экономист филиала",
        False,
        _sections(Section.OBZOR, Section.KAZNA, Section.PROIZVODSTVO, Section.SKLAD, Section.KADRY)
        | _EXPORT
        | _data("write", Section.KAZNA, Section.PROIZVODSTVO, Section.KADRY),
    ),
    RoleSeed("profil_sluzhba", "Профильная служба", True, _sections(Section.OBZOR) | _EXPORT),
    RoleSeed(ADMIN_ROLE, "Администратор", True, _ALL_SECTIONS | frozenset(p.value for p in Perm)),
    RoleSeed(
        "vnutr_kontrol",
        "Служба внутреннего контроля",
        True,
        _sections(Section.OBZOR) | {Perm.AUDIT_READ.value},
    ),
)
