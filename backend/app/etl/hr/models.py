"""HR API javoblari — faqat agregatlar (TZ 9). Javob oq ro'yxat bo'yicha o'qiladi: tuzilmada
filial `id`/`positions`, davomatda `statuses`/`summary`/`branches`. `items` (F.I.Sh. ro'yxati),
bo'lim rahbarlari va boshqa kalitlar umuman o'qilmaydi, saqlanmaydi, log'ga yozilmaydi.
Filial nomi faqat `hr.orgs` zaxira moslashtirishi uchun (buzilgan belgilar bo'lishi mumkin —
asosiy moslashtirish `id` bo'yicha); saqlanmaydi.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from app.etl.hr.client import HrApiError

# HR toifa kodi → hisobotlardagi toifa nomi (sintetik POS-1/POS-2 bilan bir xil «Руководители»,
# «Специалисты»); toifasiz lavozim — alohida qator.
CATEGORIES: dict[str | None, str] = {
    "rahbar": "Руководители", "mutaxassis": "Специалисты", "xizmatchi": "Служащие",
    "ishchi": "Рабочие", None: "Без категории"}
_CODE = re.compile(r"^[a-z0-9_]{1,40}$")


class HrFormatError(HrApiError):
    """Javob tuzilmasi kutilganidek emas (qiymatlar xato matniga yozilmaydi)."""


@dataclass(frozen=True, slots=True)
class StructureRow:
    hr_id: int
    organization: str
    category: str
    employees: int


@dataclass(frozen=True, slots=True)
class Status:
    code: str
    label: str
    kind: str


@dataclass(frozen=True, slots=True)
class BranchAttendance:
    hr_id: int
    employees: int
    by_status: dict[str, tuple[int, int]]  # kod → (odam-kun, xodimlar)


@dataclass(frozen=True, slots=True)
class AttendanceReport:
    day: date
    generated_at: datetime
    statuses: tuple[Status, ...]
    branches: tuple[BranchAttendance, ...]


def _int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HrFormatError(f"{what}: ожидается неотрицательное целое число")
    return value


def _list(data: Mapping[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise HrFormatError(f"HR API: неожиданная структура ответа ({key})")
    return value


def _map(data: Any) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise HrFormatError("HR API: неожиданная структура ответа (ожидается объект)")
    return data


def parse_total(data: Any) -> int | None:
    summary = _map(data).get("summary")
    value = summary.get("employees") if isinstance(summary, Mapping) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 \
        else None


def parse_structure(data: Any) -> list[StructureRow]:
    """Filial × toifa bo'yicha xodimlar soni (lavozimlar `category` bo'yicha yig'iladi)."""
    sums: dict[tuple[int, str, str], int] = {}
    for branch in _list(_map(data), "branches"):
        branch = _map(branch)
        hr_id = _int(branch.get("id"), "branches.id")
        name = branch.get("name")
        name = name.strip()[:200] if isinstance(name, str) else ""
        for pos in _list(branch, "positions"):
            pos = _map(pos)
            code = pos.get("category")
            if code not in CATEGORIES:
                code = None  # yangi/noma'lum toifa — «без категории»
            key = (hr_id, name, CATEGORIES[code])
            sums[key] = sums.get(key, 0) + _int(pos.get("employees_count"), "employees_count")
    return [StructureRow(i, o, c, n) for (i, o, c), n in sums.items() if n > 0]


def parse_attendance(data: Any) -> AttendanceReport:
    root = _map(data)
    try:
        generated = datetime.fromisoformat(str(root["generated_at"]))
        day = date.fromisoformat(str(_map(root["period"])["date_from"]))
    except (KeyError, ValueError) as exc:
        raise HrFormatError("HR API: нет generated_at/period.date_from") from exc
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=UTC)
    statuses = []
    for s in _list(root, "statuses"):
        s = _map(s)
        code, label, kind = s.get("code"), s.get("label"), s.get("kind")
        if not (isinstance(code, str) and _CODE.fullmatch(code) and isinstance(label, str)
                and isinstance(kind, str)):
            raise HrFormatError("HR API: статус без code/label/kind")
        statuses.append(Status(code, label.strip()[:120], kind[:24]))
    branches = []
    for b in _list(root, "branches"):
        b = _map(b)
        by_status: dict[str, tuple[int, int]] = {}
        for code, cell in _map(b.get("by_status")).items():
            if not isinstance(code, str) or not _CODE.fullmatch(code):
                raise HrFormatError("HR API: недопустимый код статуса")
            cell = _map(cell)
            by_status[code] = (_int(cell.get("days"), "days"),
                               _int(cell.get("employees"), "employees"))
        branches.append(BranchAttendance(_int(b.get("id"), "branches.id"),
                                         _int(b.get("employees"), "employees"), by_status))
    return AttendanceReport(day, generated.astimezone(UTC), tuple(statuses), tuple(branches))
