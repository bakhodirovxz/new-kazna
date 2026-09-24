"""Bo'limlar, ruxsatlar va tizim rollari (spec 3.3, TZ 1-bo'lim).

Kod — ruxsatlar ro'yxatining yagona manbai. Tizim rollari faqat BIRINCHI marta
yaratilganda seed qilinadi, keyin ularni administrator boshqaradi.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
    AUDIT_READ = "audit:read"


_PERM_TITLES: dict[Perm, str] = {
    Perm.EXPORT_CSV: "Выгрузка таблиц в CSV",
    Perm.EXPORT_XLSX: "Выгрузка в Excel (.xlsx)",
    Perm.ADMIN_USERS: "Администрирование: пользователи",
    Perm.ADMIN_ROLES: "Администрирование: должности и роли",
    Perm.ADMIN_SETTINGS: "Администрирование: настройки и пороги",
    Perm.ADMIN_ETL: "Администрирование: загрузки данных",
    Perm.ADMIN_KEYS: "Администрирование: ключи шифрования",
    Perm.AUDIT_READ: "Просмотр журнала аудита",
}

PERMISSIONS: dict[str, str] = {
    **{section_perm(s): f"Раздел «{t}»: просмотр" for s, t in SECTION_TITLES.items()},
    **{p.value: t for p, t in _PERM_TITLES.items()},
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
_EXPORT = frozenset({Perm.EXPORT_CSV.value, Perm.EXPORT_XLSX.value})

ADMIN_ROLE = "admin"
ADMIN_GUARANTEED = frozenset({Perm.ADMIN_USERS.value, Perm.ADMIN_ROLES.value})

ROLE_SEEDS: tuple[RoleSeed, ...] = (
    RoleSeed("rukovodstvo", "Руководство", True, _ALL_SECTIONS | _EXPORT),
    RoleSeed(
        "nach_otdela",
        "Начальник отдела финансирования и контроля денежных потоков",
        True,
        _ALL_SECTIONS | _EXPORT,
    ),
    RoleSeed(
        "spec_kazna",
        "Специалист казначейства",
        True,
        _sections(Section.OBZOR, Section.KAZNA, Section.KREDITY, Section.FINMODEL) | _EXPORT,
    ),
    RoleSeed(
        "economist_filiala",
        "Экономист филиала",
        False,
        _sections(Section.OBZOR, Section.KAZNA, Section.PROIZVODSTVO, Section.SKLAD, Section.KADRY)
        | _EXPORT,
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
