from pathlib import Path

from sqlalchemy import text

from app.etl.db import etl_transaction
from app.etl.file_connector import FileConnector
from app.etl.runner import Runner
from app.etl.types import Mode
from tests.etl_helpers import TEST_AS_OF, new_source, new_tag, purge_source


def _write(folder: Path, name: str, *lines: str) -> None:
    (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _templates(folder: Path, tag: str, method: str = "eshop") -> None:
    code = f"T-{tag}"
    _write(folder, "dim_branch.csv", "code;name;short_name;kind;capacity_mw;sort_order",
           f"{code};Тестовая ГЭС;Т;ges;100;99")
    _write(folder, "dim_nomenclature.csv", "code;name;category;unit;enbt_code",
           f"PS-{tag};Запасные части;Запасные части;—;")
    _write(folder, "dim_counterparty.csv", "code;name;kind;inn",
           f"S-{tag};ООО «Гидромонтаж Сервис»;supplier;301234567")
    _write(folder, "fact_procurement.csv",
           "doc_type;src_id;date;branch_code;nom_code;cp_code;lot_no;method;status;"
           "start_price;contract_price;procedure_days",
           f"procurement_plan;PLAN-{tag}-2026;2026-01-01;{code};;;ПЛАН-2026;plan;план;"
           "1000.00;;",
           f"portal_lot;LOT-{tag}-1;2026-08-10;{code};PS-{tag};S-{tag};2026-0101;{method};"
           "договор заключён;100.00;90.00;12",
           f"portal_lot;LOT-{tag}-2;2026-07-01;{code};PS-{tag};;2026-0102;contest;объявлен;"
           "80.00;;")
    _write(folder, "dim_source.csv", "code;name;kind", f"SRC-{tag};Бюджетные средства;budget")
    _write(folder, "dim_object.csv",
           "code;name;program_code;work_type;commissioning_year;total_cost;source_code",
           f"OBJ-{tag};Модернизация гидроагрегатов;АИП-2026-01;modernization;2026;1000.00;"
           f"SRC-{tag}")
    _write(folder, "fact_investment.csv",
           "doc_type;src_id;date;branch_code;object_code;source_code;plan;fact;physical_pct;"
           "advance;advance_date_id",
           f"aip_opening;OPEN-{tag};2025-01-01;{code};OBJ-{tag};SRC-{tag};0;300.00;;0;",
           f"aip_month;INV-{tag}-202608;2026-08-01;{code};OBJ-{tag};SRC-{tag};60.00;40.00;"
           "0.4000;30.00;20260601",
           f"aip_month;INV-{tag}-202612;2026-12-01;{code};OBJ-{tag};SRC-{tag};60.00;0;;0;")
    _write(folder, "fact_object_stage.csv",
           "doc_type;src_id;date;branch_code;object_code;stage_no;stage_name;fact_date_id",
           f"aip_stage;STG-{tag}-1;2026-03-15;{code};OBJ-{tag};1;"
           "Проектно-сметная документация;20260310")
    _write(folder, "dim_position.csv", "code;category;department",
           f"POS-{tag};Оперативный персонал;Производственные подразделения")
    _write(folder, "fact_hr.csv",
           "doc_type;src_id;date;branch_code;pos_code;headcount_plan;headcount_fact;payroll;"
           "hired;fired;overtime_hours",
           f"hr_month;HR-{tag}-202608;2026-08-31;{code};POS-{tag};90;81;0;2;3;400.0")


def test_s4_templates_load(tmp_path: Path) -> None:
    source = new_source()
    tag = new_tag()
    try:
        _templates(tmp_path, tag)
        result = Runner(FileConnector(tmp_path, source=source), mode=Mode.FULL,
                        today=TEST_AS_OF, sleep=lambda _: None).run()
        assert result.status == "success", result
        with etl_transaction() as conn:
            branch_id = conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": f"T-{tag}"}).scalar_one()
            params = {"b": result.build_id, "br": branch_id}
            lots = conn.execute(text(
                "SELECT lot_no, overdue FROM mart.agg_procurement_lots WHERE build_id = :b "
                "AND branch_id = :br ORDER BY lot_no"), params).all()
            plan = conn.execute(text(
                "SELECT plan FROM mart.agg_procurement_plan WHERE build_id = :b "
                "AND branch_id = :br AND month_id = 202601"), params).scalar_one()
            inv = conn.execute(text(
                "SELECT month_id, plan, physical_pct, advance FROM mart.agg_investment_month "
                "WHERE build_id = :b AND branch_id = :br AND month_id IN (202608, 202612) "
                "ORDER BY month_id"), params).all()
            stage = conn.execute(text(
                "SELECT done FROM mart.agg_object_stages WHERE build_id = :b "
                "AND branch_id = :br"), params).scalar_one()
            hr = conn.execute(text(
                "SELECT headcount_fact FROM mart.agg_hr_month WHERE build_id = :b "
                "AND branch_id = :br AND month_id = 202608"), params).scalar_one()
        assert [(r.lot_no, r.overdue) for r in lots] == [("2026-0101", False),
                                                         ("2026-0102", True)]
        assert float(plan) == 1000.0 and float(hr) == 81.0 and stage is True
        assert [(r.month_id, float(r.plan)) for r in inv] == [(202608, 60.0), (202612, 60.0)]
        assert (float(inv[0].physical_pct), float(inv[0].advance)) == (0.4, 30.0)
    finally:
        purge_source(source)


def test_bad_method_rejects_row(tmp_path: Path) -> None:
    """Noma'lum usul: qator rad etiladi (etl_error), qolgan qatorlar e'lon qilinadi; bazadagi
    CHECK (fact_procurement_method_ck) — qo'shimcha to'siq (test_s4_prereq)."""
    source = new_source()
    try:
        tag = new_tag()
        _templates(tmp_path, tag, method="auction")
        result = Runner(FileConnector(tmp_path, source=source), mode=Mode.FULL,
                        today=TEST_AS_OF, sleep=lambda _: None).run()
        assert result.status == "success", result
        with etl_transaction() as conn:
            lots = conn.execute(text(
                "SELECT src_id FROM dwh.fact_procurement WHERE src_system = :s "
                "AND doc_type = 'portal_lot' ORDER BY src_id"), {"s": source}).scalars().all()
            errors = conn.execute(text(
                "SELECT count(*) FROM core.etl_error WHERE run_id = :r "
                "AND target = 'fact_procurement' AND severity = 'error'"),
                {"r": result.run_id}).scalar_one()
        assert lots == [f"LOT-{tag}-2"] and errors == 1
    finally:
        purge_source(source)
