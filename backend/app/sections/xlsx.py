"""«Таблица Excel» (TZ 5): 4 varaqli .xlsx — Сводка, Детализация, По месяцам, План-факт.

Matn kataklari (1C'dan kelgan nomlar ham) hech qachon formula sifatida saqlanmaydi: `=`, `+`, `-`,
`@`, tab, CR, LF bilan boshlansa (bo'shliqlardan keyin ham) — katak turi "s" va quotePrefix.
"""

from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from app.meta.periods import MONTHS
from app.sections.queries.cash import MonthPoint
from app.sections.queries.payments import PlanFactRow
from app.sections.schemas import ObzorExcelOut

SHEETS = ("Сводка", "Детализация", "По месяцам", "План-факт")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")
ACTIVITY = {"centralized": "Централизованная", "operating": "Операционная",
            "investing": "Инвестиционная"}
DIRECTION = {"in": "Поступление", "out": "Расходование"}
NUMBER = "#,##0.0"
BOLD = Font(bold=True)


def _r1(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _put(ws: Worksheet, row: int, col: int, value: Any, *, bold: bool = False) -> None:
    cell = ws.cell(row=row, column=col)
    cell.value = value
    if isinstance(value, str) and value.lstrip().startswith(FORMULA_PREFIXES):
        cell.data_type = "s"
        cell.quotePrefix = True
    if isinstance(value, float):
        cell.number_format = NUMBER
    if bold:
        cell.font = BOLD


def _table(ws: Worksheet, start: int, header: list[str], rows: list[list[Any]],
           widths: list[int]) -> None:
    for col, title in enumerate(header, start=1):
        _put(ws, start, col, title, bold=True)
    for r, values in enumerate(rows, start=start + 1):
        for col, value in enumerate(values, start=1):
            _put(ws, r, col, value)
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=start, column=col).column_letter].width = width


def build_workbook(data: ObzorExcelOut, plan: list[PlanFactRow], months: list[MonthPoint],
                   scope: str) -> bytes:
    wb = Workbook()
    svod = wb.active
    svod.title = SHEETS[0]
    _put(svod, 1, 1, f"Движение денежных средств, {scope}, {data.period.label}, млн сум",
         bold=True)
    rows = [[b.name, _r1(b.opening), _r1(b.inflow), _r1(b.outflow), _r1(b.net), _r1(b.closing),
             _r1(b.diff)] for b in data.branches]
    t = data.total
    rows.append(["Итого", _r1(t.opening), _r1(t.inflow), _r1(t.outflow), _r1(t.net),
                 _r1(t.closing), _r1(t.diff)])
    _table(svod, 3, ["Филиал", "Начальный остаток", "Поступления", "Расходование",
                     "Чистый поток", "Конечный остаток", "Разница"], rows,
           [34, 19, 19, 19, 19, 19, 19])

    detail = wb.create_sheet(SHEETS[1])
    _table(detail, 1, ["Филиал", "Направление", "Статья", "Вид деятельности", "Сумма, млн сум"],
           [[d.branch_name, DIRECTION[d.direction], d.item_name,
             ACTIVITY.get(d.activity, d.activity) if d.direction == "out" else "–",
             _r1(d.amount)] for d in data.detail], [34, 15, 44, 19, 17])

    by_month = wb.create_sheet(SHEETS[2])
    _table(by_month, 1, ["Месяц", "Поступления", "Расходование", "Чистый поток"],
           [[MONTHS[p.month_id % 100 - 1], _r1(p.inflow), _r1(p.outflow),
             _r1(p.inflow - p.outflow)] for p in months], [13, 17, 17, 17])

    plan_fact = wb.create_sheet(SHEETS[3])
    _table(plan_fact, 1, ["Статья", "Вид деятельности", "План", "Факт", "Исполнение, %",
                          "Отклонение"],
           [[r.name, ACTIVITY.get(r.activity, r.activity), _r1(r.plan), _r1(r.fact),
             None if r.execution is None else round(r.execution * 100, 1), _r1(r.deviation)]
            for r in plan], [44, 19, 15, 15, 14, 15])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
