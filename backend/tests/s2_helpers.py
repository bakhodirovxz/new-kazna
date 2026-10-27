"""S2 testlari uchun qo'lda hisoblanadigan kredit ssenariysi (jadval — rejaning 2-vazifasida)
va umumiy yordamchilar (sozlama/qoida versiyalari, filial doirasidagi «Кредиты» roli)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text

from app.auth.models import Role, RolePermission
from app.core.db import get_engine, new_session
from app.etl.db import etl_transaction
from tests.etl_helpers import branch_row, merge_all, new_tag, open_run, stage
from tests.s1_helpers import rebuild

FX = "XTL"  # ISO 4217 da yo'q test kodi (S1 ssenariysidagi XTS bilan to'qnashmaydi)
KREDITY_BRANCH_ROLE = "t_kredity_branch"


@dataclass(frozen=True, slots=True)
class LoanScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    empty_branch_id: int
    run_id: int
    build_id: int
    loan_a: int
    loan_b: int


def loan_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    empty = branch_row(f"{tag}E", name=f"Тестовая ГЭС без кредитов {tag}")
    code = branch["code"]
    a, b, c = f"LA-{tag}", f"LB-{tag}", f"LC-{tag}"

    def row(src_id: str, loan: str, day: int, principal: float, interest: float,
            balance: float) -> dict[str, Any]:
        return {"doc_type": "loan_schedule", "src_id": src_id, "date_id": day,
                "branch_code": code, "loan_code": loan, "principal": principal,
                "interest": interest, "balance": balance}

    return {
        "dim_branch": [branch, empty],
        "dim_loan": [
            {"code": a, "creditor": f"Тест кредитор А {tag}", "project": "Модернизация ГЭС",
             "currency": FX, "rate": 0.05, "grace_until": "2026-01-01",
             "maturity": "2028-12-31", "amount_uzs": 10000, "branch_code": code},
            {"code": b, "creditor": f"Тест кредитор Б {tag}", "project": "Оборотные средства",
             "currency": "UZS", "rate": 0.18, "grace_until": None, "maturity": "2027-12-31",
             "amount_uzs": 500, "branch_code": code},
            {"code": c, "creditor": f"Тест кредитор В {tag}", "project": "Без графика",
             "currency": "UZS", "rate": 0.1, "grace_until": None, "maturity": "2030-12-31",
             "amount_uzs": 50, "branch_code": code},
        ],
        "fx_rate": [{"currency": FX, "date_id": 20260801, "rate": 1000},
                    {"currency": FX, "date_id": 20260901, "rate": 1100}],
        "fact_loan_schedule": [
            row("a1", a, 20260315, 1, 0.5, 9), row("a2", a, 20260915, 1, 0.46, 8),
            row("a3", a, 20270315, 1, 0.4, 7), row("a4", a, 20280315, 7, 0.35, 0),
            row("b1", b, 20260610, 100, 30, 400), row("b2", b, 20261010, 100, 18, 300),
            row("b3", b, 20271010, 300, 18, 0),
        ],
    }


def loan_scenario(source: str, *, publish: bool = False) -> LoanScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, loan_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    with etl_transaction() as conn:
        branches = dict(conn.execute(text(
            "SELECT code, branch_id FROM dwh.dim_branch WHERE code IN (:a, :b)"),
            {"a": f"T-{tag}", "b": f"T-{tag}E"}).all())
        loans = dict(conn.execute(text(
            "SELECT code, loan_id FROM dwh.dim_loan WHERE code IN (:a, :b)"),
            {"a": f"LA-{tag}", "b": f"LB-{tag}"}).all())
    return LoanScenario(source, tag, int(branches[f"T-{tag}"]), f"T-{tag}",
                        int(branches[f"T-{tag}E"]), run_id, build_id, int(loans[f"LA-{tag}"]),
                        int(loans[f"LB-{tag}"]))


def put_rule(code: str, **changes: Any) -> None:
    """core.alert_rules ga yangi versiya (S1 testidagi yordamchi bilan bir xil)."""
    with get_engine("app").begin() as conn:
        row = conn.execute(text("SELECT * FROM core.alert_rules WHERE code = :c AND is_current"),
                           {"c": code}).mappings().one()
        data = {**dict(row), **changes}
        conn.execute(text("UPDATE core.alert_rules SET is_current = false "
                          "WHERE code = :c AND is_current"), {"c": code})
        conn.execute(text(
            "INSERT INTO core.alert_rules (code, version, title, section, page, threshold, level, "
            "enabled) VALUES (:code, :v, :title, :section, :page, CAST(:th AS jsonb), :level, "
            ":en)"),
            {"code": code, "v": row["version"] + 1, "title": data["title"],
             "section": data["section"], "page": data["page"],
             "th": json.dumps(data["threshold"]), "level": data["level"],
             "en": data["enabled"]})


def kredity_branch_role() -> str:
    """Filial doirasidagi (scope_all = false) va «Кредиты»ni ko'ra oladigan test roli —
    seed rollarida bunday rol yo'q (spec_kazna hamma filialni ko'radi)."""
    with new_session() as s:
        exists = s.execute(select(Role.id).where(Role.code == KREDITY_BRANCH_ROLE)).scalar()
        if exists is None:
            role = Role(code=KREDITY_BRANCH_ROLE, name="Тест: кредиты филиала", scope_all=False)
            s.add(role)
            s.flush()
            s.add(RolePermission(role_id=role.id, permission_code="section:kredity:view"))
            s.commit()
    return KREDITY_BRANCH_ROLE
