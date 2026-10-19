"""9 bo'lim va ularning chap menyusi (TZ 5-bo'lim jadvali), guruhlar (TZ 6 «Навигация»).

Sahifa id'lari tasdiqlangan prototip bilan bir xil (URL: #kazna/svod?br=3&per=m05).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.auth.permissions import SECTION_TITLES, Section, section_perm
from app.meta.schemas import MenuGroupOut, MenuOut, MenuPageOut, MenuSectionOut


@dataclass(frozen=True, slots=True)
class MenuPage:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class MenuSection:
    section: Section
    group: str | None
    pages: tuple[MenuPage, ...]


P = MenuPage
SVOD = P("svod", "Сводка")
GROUP_ORDER: tuple[str | None, ...] = (None, "Финансы", "Обеспечение", "Производство", "Персонал")

MENU: tuple[MenuSection, ...] = (
    MenuSection(Section.OBZOR, None, (
        SVOD, P("vnimanie", "Требует внимания"), P("postup", "Поступления"),
        P("rasxod", "Расходование"), P("excel", "Таблица Excel"))),
    MenuSection(Section.KAZNA, "Финансы", (
        SVOD, P("platezhi", "Исполнение платежей"), P("calendar", "Платёжный календарь"),
        P("dogovory", "Договоры и задолженность"), P("celevye", "Целевые средства"))),
    MenuSection(Section.KREDITY, "Финансы", (
        SVOD, P("reestr", "Реестр кредитов"), P("grafik", "График платежей"))),
    MenuSection(Section.FINMODEL, "Финансы", (
        SVOD, P("dohody", "Доходы и расходы"), P("dolg", "Инвестиции и долг"),
        P("scenarii", "Сценарии"))),
    MenuSection(Section.ZAKUPKI, "Обеспечение", (
        SVOD, P("loty", "Лоты"), P("postavshiki", "Договоры и поставщики"),
        P("ekonomiya", "Экономия"))),
    MenuSection(Section.SKLAD, "Обеспечение", (
        SVOD, P("ostatki", "Остатки по складам"), P("minimum", "Минимальный запас"),
        P("nelikvid", "Неликвиды"))),
    MenuSection(Section.PROIZVODSTVO, "Производство", (
        SVOD, P("stancii", "Выработка по станциям"), P("realiz", "Реализация"))),
    MenuSection(Section.INVESTICII, "Производство", (
        SVOD, P("obekty", "Объекты"), P("istochniki", "Источники и освоение"),
        P("riski", "Сроки и риски"))),
    MenuSection(Section.KADRY, "Персонал", (
        SVOD, P("chislennost", "Численность"), P("fot", "Оплата труда"),
        P("dvizhenie", "Движение кадров"))),
)


def build_menu(permissions: frozenset[str]) -> MenuOut:
    groups: list[MenuGroupOut] = []
    for group in GROUP_ORDER:
        sections = [
            MenuSectionOut(
                id=item.section.value,
                title=SECTION_TITLES[item.section],
                pages=[MenuPageOut(id=p.id, title=p.title) for p in item.pages],
            )
            for item in MENU
            if item.group == group and section_perm(item.section) in permissions
        ]
        if sections:
            groups.append(MenuGroupOut(title=group, sections=sections))
    return MenuOut(groups=groups)
