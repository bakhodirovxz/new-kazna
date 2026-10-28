"""S5 test yordamchilari: финмодель kirishlari ssenariysi va допущения'ni vaqtincha o'zgartirish."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.core.db import get_engine
from tests.etl_helpers import branch_row, cash_row, merge_all, new_tag, open_run, stage
from tests.s1_helpers import rebuild

FX, NO_RATE = "XFM", "XFN"


@dataclass(frozen=True, slots=True)
class FinScenario:
    source: str
    tag: str
    run_id: int
    build_id: int
    items: dict[str, str]  # rol → statya kodi: op, ex, iv, tx


def finmodel_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag, capacity_mw=120.5, kind="ges")
    code = branch["code"]
    op, ex, iv, tx = f"OP-{tag}", f"EX-{tag}", f"IV-{tag}", f"TX-{tag}"
    bank = f"ACC-{tag}"
    src, obj = f"SF-{tag}", f"OF-{tag}"
    lu, lf, ln = f"LU-{tag}", f"LF-{tag}", f"LN-{tag}"

    def item(item_code: str, activity: str) -> dict[str, Any]:
        return {"code": item_code, "name": f"Статья {item_code}", "activity": activity,
                "direction": "out", "sort_order": 900}

    def inv(src_id: str, day: int, plan: float, fact: float = 0,
            doc: str = "aip_month") -> dict[str, Any]:
        return {"doc_type": doc, "src_id": src_id, "date_id": day, "branch_code": code,
                "object_code": obj, "source_code": src, "plan": plan, "fact": fact,
                "physical_pct": None, "advance": 0, "advance_date_id": None}

    def loan(loan_code: str, currency: str) -> dict[str, Any]:
        return {"code": loan_code, "creditor": f"Тест кредитор {loan_code}",
                "project": "Финмодель тест", "currency": currency, "rate": 0.05,
                "grace_until": None, "maturity": "2030-12-31", "amount_uzs": 1000,
                "branch_code": code}

    def sched(src_id: str, loan_code: str, day: int, principal: float,
              interest: float) -> dict[str, Any]:
        return {"doc_type": "loan_schedule", "src_id": src_id, "date_id": day,
                "branch_code": code, "loan_code": loan_code, "principal": principal,
                "interest": interest, "balance": 0}

    return {
        "dim_branch": [branch],
        "dim_item": [item(op, "operating"), item(ex, "operating"), item(iv, "investing"),
                     item(tx, "operating")],
        "dim_bank": [{"code": bank, "bank_name": "Тест банк", "currency": "UZS"}],
        "dim_source": [{"code": src, "name": f"Бюджет {tag}", "kind": "budget"}],
        "dim_object": [{"code": obj, "name": f"Объект {tag}", "program_code": "АИП-Ф-1",
                        "work_type": "new", "commissioning_year": 2028, "total_cost": 5000,
                        "source_code": src}],
        "dim_loan": [loan(lu, "UZS"), loan(lf, FX), loan(ln, NO_RATE)],
        "fx_rate": [{"currency": FX, "date_id": 20260801, "rate": 1000},
                    {"currency": FX, "date_id": 20260901, "rate": 1100},
                    {"currency": FX, "date_id": 20261001, "rate": 1300}],
        "fact_cashflow": [
            cash_row("c1", 20260315, code, 1200, item_code=op),
            cash_row("c2", 20250915, code, 100, item_code=op),
            cash_row("c3", 20250831, code, 700, item_code=op),
            cash_row("c4", 20260910, code, 400, item_code=op),
            cash_row("c5", 20260401, code, 300, item_code=ex),
            cash_row("c6", 20260402, code, 500, item_code=iv),
            cash_row("c7", 20260403, code, 250, item_code=tx),
            cash_row("c8", 20260404, code, 999, item_code=op, direction="in"),
        ],
        "fact_balance": [
            {"doc_type": "statement", "src_id": "b1", "date_id": 20260831, "branch_code": code,
             "bank_code": bank, "balance": 650},
            {"doc_type": "statement", "src_id": "b2", "date_id": 20260920, "branch_code": code,
             "bank_code": bank, "balance": 800},
        ],
        "fact_investment": [
            inv("i0", 20250101, 0, 300, doc="aip_opening"), inv("i1", 20260301, 100),
            inv("i2", 20261001, 200), inv("i3", 20270101, 500), inv("i4", 20330101, 999),
        ],
        "fact_loan_schedule": [
            sched("u1", lu, 20261010, 100, 30), sched("u2", lu, 20271010, 300, 18),
            sched("f1", lf, 20260915, 1, 0.5), sched("f2", lf, 20270315, 2, 0.4),
            sched("n1", ln, 20261201, 5, 1),
        ],
    }


def finmodel_scenario(source: str, *, publish: bool = False) -> FinScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, finmodel_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    items = {"op": f"OP-{tag}", "ex": f"EX-{tag}", "iv": f"IV-{tag}", "tx": f"TX-{tag}"}
    return FinScenario(source, tag, run_id, build_id, items)


def fin_value(scenario: str, year: int, key: str) -> Decimal:
    with get_engine("app").connect() as conn:
        return Decimal(conn.execute(text(
            "SELECT value FROM core.fin_assumptions WHERE scenario = :s AND year = :y "
            "AND key = :k AND is_current"), {"s": scenario, "y": year, "k": key}).scalar_one())


def put_fin(scenario: str, year: int, key: str, value: Decimal) -> None:
    """core.fin_assumptions ga yangi versiya (admin `update_fin_assumptions` bilan bir xil)."""
    params = {"s": scenario, "y": year, "k": key}
    with get_engine("app").begin() as conn:
        version = conn.execute(text(
            "SELECT max(version) FROM core.fin_assumptions WHERE scenario = :s AND year = :y "
            "AND key = :k"), params).scalar_one()
        conn.execute(text("UPDATE core.fin_assumptions SET is_current = false WHERE scenario = :s "
                          "AND year = :y AND key = :k AND is_current"), params)
        conn.execute(text(
            "INSERT INTO core.fin_assumptions (scenario, year, key, version, value) "
            "VALUES (:s, :y, :k, :v, :val)"), {**params, "v": version + 1, "val": value})
