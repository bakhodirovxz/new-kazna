from pathlib import Path

from sqlalchemy import text

from app.etl.db import etl_transaction
from app.etl.file_connector import FileConnector
from app.etl.runner import Runner
from app.etl.types import Mode
from tests.etl_helpers import TEST_AS_OF, new_source, new_tag, purge_source


def test_plan_and_sales_templates_load(tmp_path: Path) -> None:
    source = new_source()
    tag = new_tag()
    code = f"T-{tag}"
    try:
        (tmp_path / "dim_branch.csv").write_text(
            "code;name;short_name;kind;capacity_mw;sort_order\n"
            f"{code};Тестовая ГЭС;Т;ges;100;99\n", encoding="utf-8")
        (tmp_path / "dim_counterparty.csv").write_text(
            "code;name;kind;inn\n"
            f"CPB-{tag};АО «Национальные электрические сети Узбекистана»;buyer;301234567\n",
            encoding="utf-8")
        (tmp_path / "fact_generation.csv").write_text(
            "doc_type;src_id;date;branch_code;generation;own_needs;supply;plan;work_hours\n"
            f"generation_plan;PLAN-{tag}-202609;2026-09-01;{code};0;0;0;1.5;\n",
            encoding="utf-8")
        (tmp_path / "fact_energy_sales.csv").write_text(
            "doc_type;src_id;date;branch_code;cp_code;accrued;paid;volume\n"
            f"energy_sales;ES-{tag}-202608;2026-08-31;{code};CPB-{tag};1200.00;900.00;1.760\n",
            encoding="utf-8")
        result = Runner(FileConnector(tmp_path, source=source), mode=Mode.FULL,
                        today=TEST_AS_OF, sleep=lambda _: None).run()
        assert result.status == "success", result
        with etl_transaction() as conn:
            branch_id = conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": code}).scalar_one()
            plan = conn.execute(text(
                "SELECT plan, plan_full FROM mart.agg_generation_month WHERE build_id = :b "
                "AND branch_id = :br AND month_id = 202609"),
                {"b": result.build_id, "br": branch_id}).one()
            sales = conn.execute(text(
                "SELECT accrued, paid FROM mart.agg_energy_sales_month WHERE build_id = :b "
                "AND branch_id = :br AND month_id = 202608"),
                {"b": result.build_id, "br": branch_id}).one()
        assert (float(plan.plan), float(plan.plan_full)) == (1.2, 1.5)
        assert (float(sales.accrued), float(sales.paid)) == (1200.0, 900.0)
    finally:
        purge_source(source)
