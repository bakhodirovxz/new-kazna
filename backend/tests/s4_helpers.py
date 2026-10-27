"""S4 testlari uchun qo'lda hisoblanadigan ssenariylar (jadvallar — rejaning 4–6-vazifalarida)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text

from app.auth.models import Role, RolePermission
from app.core.db import get_engine, new_session
from app.etl.db import etl_transaction
from tests.etl_helpers import (
    branch_row,
    cash_row,
    merge_all,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.s1_helpers import rebuild

DONE, ANNOUNCED, EVAL, CANCELLED = "договор заключён", "объявлен", "на оценке", "отменён"


def _branch_id(code: str) -> int:
    with etl_transaction() as conn:
        return int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                {"c": code}).scalar_one())


@dataclass(frozen=True, slots=True)
class ProcScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    run_id: int
    build_id: int


def procurement_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    code = branch["code"]

    def nom(key: str, subject: str) -> dict[str, Any]:
        return {"code": f"{key}-{tag}", "name": subject, "category": subject, "unit": "—",
                "enbt_code": None}

    def lot(src: str, day: int, method: str, status: str, start: float,
            contract: float | None, days: int | None, sup: str | None,
            subj: str) -> dict[str, Any]:
        return {"doc_type": "portal_lot", "src_id": src, "date_id": day, "branch_code": code,
                "nom_code": f"{subj}-{tag}", "cp_code": f"{sup}-{tag}" if sup else None,
                "lot_no": src.upper(), "method": method, "status": status,
                "start_price": start, "contract_price": contract, "procedure_days": days}

    def plan(src: str, day: int, amount: float) -> dict[str, Any]:
        return {"doc_type": "procurement_plan", "src_id": src, "date_id": day,
                "branch_code": code, "nom_code": None, "cp_code": None, "lot_no": "ПЛАН",
                "method": "plan", "status": "план", "start_price": amount,
                "contract_price": None, "procedure_days": None}

    return {
        "dim_branch": [branch],
        "dim_nomenclature": [nom("SP1", "Запасные части"), nom("SP2", "Ремонтные услуги"),
                             nom("SP3", "Строительно-монтажные работы")],
        "dim_counterparty": [
            {"code": f"S1-{tag}", "name": f"ООО «Поставщик-1 {tag}»", "kind": "supplier",
             "inn": "301111111"},
            {"code": f"S2-{tag}", "name": f"ООО «Поставщик-2 {tag}»", "kind": "supplier",
             "inn": "301111112"}],
        "fact_procurement": [
            lot("l1", 20260810, "eshop", DONE, 100, 90, 12, "S1", "SP1"),
            lot("l2", 20260820, "direct", DONE, 50, 50, 5, "S2", "SP2"),
            lot("l3", 20260905, "tender", DONE, 200, 170, 60, "S1", "SP3"),
            lot("l4", 20260701, "contest", ANNOUNCED, 80, None, None, None, "SP3"),
            lot("l5", 20260910, "eshop", EVAL, 30, None, None, None, "SP1"),
            lot("l6", 20260815, "exchange", CANCELLED, 40, None, None, None, "SP1"),
            lot("l7", 20260210, "eshop", DONE, 60, 57, 10, "S2", "SP1"),
            lot("l8", 20250812, "direct", DONE, 20, 20, 4, "S2", "SP2"),
            plan("p26", 20260101, 1000), plan("p25", 20250101, 500),
        ],
    }


def procurement_scenario(source: str, *, publish: bool = False) -> ProcScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, procurement_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    return ProcScenario(source, tag, _branch_id(f"T-{tag}"), f"T-{tag}", run_id, build_id)


@dataclass(frozen=True, slots=True)
class InvScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    run_id: int
    build_id: int
    obj_a: int
    obj_b: int


def investment_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    code = branch["code"]
    a, b, sa, sb = f"OA-{tag}", f"OB-{tag}", f"SA-{tag}", f"SB-{tag}"

    def row(src: str, obj: str, day: int, plan: float, fact: float,
            phys: float | None = None, adv: float = 0, adv_date: int | None = None,
            doc: str = "aip_month") -> dict[str, Any]:
        return {"doc_type": doc, "src_id": src, "date_id": day, "branch_code": code,
                "object_code": obj, "source_code": sa if obj == a else sb, "plan": plan,
                "fact": fact, "physical_pct": phys, "advance": adv, "advance_date_id": adv_date}

    def stg(n: int, name: str, day: int, fact: int | None) -> dict[str, Any]:
        return {"doc_type": "aip_stage", "src_id": f"st{n}", "date_id": day,
                "branch_code": code, "object_code": a, "stage_no": n, "stage_name": name,
                "fact_date_id": fact}

    return {
        "dim_branch": [branch],
        "dim_source": [{"code": sa, "name": f"Бюджет тест {tag}", "kind": "budget"},
                       {"code": sb, "name": f"МФИ тест {tag}", "kind": "ifi"}],
        "dim_object": [
            {"code": a, "name": f"Объект А {tag}", "program_code": "АИП-Т-1",
             "work_type": "modernization", "commissioning_year": 2026, "total_cost": 1000,
             "source_code": sa},
            {"code": b, "name": f"Объект Б {tag}", "program_code": "АИП-Т-2",
             "work_type": "reconstruction", "commissioning_year": 2027, "total_cost": 500,
             "source_code": sb}],
        "fact_investment": [
            row("a0", a, 20250101, 0, 300, doc="aip_opening"),
            row("a1", a, 20251001, 100, 100),
            row("a7", a, 20260701, 60, 50, 0.40, 30, 20260601),
            row("a8", a, 20260801, 60, 40, None, 30, 20260601),
            row("a9", a, 20260901, 60, 20, 0.45, 0, None),
            row("a10", a, 20261001, 60, 0),
            row("b0", b, 20250101, 0, 100, doc="aip_opening"),
            row("b8", b, 20260801, 100, 90, 0.05, 20, 20260510),
            row("b9", b, 20260901, 100, 30, None, 20, 20260510),
        ],
        "fact_object_stage": [
            stg(1, "Проектно-сметная документация", 20260315, 20260310),
            stg(2, "Тендер и договор", 20260615, 20260720),
            stg(3, "Строительно-монтажные работы", 20260915, None),
            stg(4, "Ввод в эксплуатацию", 20261215, None),
        ],
    }


def investment_scenario(source: str, *, publish: bool = False) -> InvScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, investment_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    with etl_transaction() as conn:
        objs = dict(conn.execute(text(
            "SELECT code, object_id FROM dwh.dim_object WHERE code IN (:a, :b)"),
            {"a": f"OA-{tag}", "b": f"OB-{tag}"}).all())
    return InvScenario(source, tag, _branch_id(f"T-{tag}"), f"T-{tag}", run_id, build_id,
                       int(objs[f"OA-{tag}"]), int(objs[f"OB-{tag}"]))


@dataclass(frozen=True, slots=True)
class HrScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    run_id: int
    build_id: int
    salary_code: str


def hr_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    code = branch["code"]
    salary = f"SAL-{tag}"

    def hr(src: str, day: int, pos: str, plan: int, fact: int, hired: int, fired: int,
           overtime: float) -> dict[str, Any]:
        return {"doc_type": "hr_month", "src_id": src, "date_id": day, "branch_code": code,
                "pos_code": f"{pos}-{tag}", "headcount_plan": plan, "headcount_fact": fact,
                "payroll": 0, "hired": hired, "fired": fired, "overtime_hours": overtime}

    return {
        "dim_branch": [branch],
        "dim_position": [{"code": f"HP1-{tag}", "category": "Руководители", "department": "—"},
                         {"code": f"HP2-{tag}", "category": "Оперативный персонал",
                          "department": "—"}],
        "dim_item": [{"code": salary, "name": f"Заработная плата тест {tag}",
                      "activity": "operating", "direction": "out", "sort_order": 999}],
        "fact_hr": [
            hr("h71", 20260731, "HP1", 10, 9, 0, 1, 15),
            hr("h72", 20260731, "HP2", 90, 82, 1, 1, 300),
            hr("hx", 20260815, "HP2", 90, 85, 0, 0, 0),
            hr("h81", 20260831, "HP1", 10, 9, 1, 0, 20),
            hr("h82", 20260831, "HP2", 90, 81, 2, 3, 400),
            hr("h91", 20260924, "HP1", 10, 10, 1, 0, 10),
            hr("h92", 20260924, "HP2", 90, 80, 1, 2, 200),
        ],
        "fact_cashflow": [
            cash_row("c1", 20260715, code, 170, item_code=salary),
            cash_row("c2", 20260815, code, 180, item_code=salary),
            cash_row("c3", 20260910, code, 150, item_code=salary),
            cash_row("c4", 20260820, code, 420),
            cash_row("c5", 20260912, code, 100),
        ],
    }


def hr_scenario(source: str, *, publish: bool = False) -> HrScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, hr_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    return HrScenario(source, tag, _branch_id(f"T-{tag}"), f"T-{tag}", run_id, build_id,
                      f"SAL-{tag}")


def section_branch_role(section: str) -> str:
    """Filial doirasidagi (scope_all = false) va faqat bitta bo'limni ko'radigan test roli —
    seed rollarida «Закупки»/«Инвестиции» uchun bunday rol yo'q."""
    code = f"t_{section}_branch"
    with new_session() as s:
        exists = s.execute(select(Role.id).where(Role.code == code)).scalar()
        if exists is None:
            role = Role(code=code, name=f"Тест: {section} филиала", scope_all=False)
            s.add(role)
            s.flush()
            s.add(RolePermission(role_id=role.id, permission_code=f"section:{section}:view"))
            s.commit()
    return code



def purge_s4(source: str) -> None:
    """Modul darajasidagi ssenariyni tozalash: foydalanuvchilarning filial biriktirishlari
    (core.position_branches) dim_branch'ni ushlab turmasin. dim_branch RLS ostida — id'lar
    etl ulanishi bilan olinadi."""
    with etl_transaction() as conn:
        ids = list(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE src_system = :s"),
                                {"s": source}).scalars())
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.position_branches WHERE branch_id = ANY(:ids)"),
                     {"ids": ids})
    purge_source(source)
