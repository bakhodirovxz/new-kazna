from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.auth.permissions import Perm
from app.core.config import Settings, get_settings
from app.core.integrations import INTEGRATIONS
from app.core.sysconfig import REGISTRY
from app.dwh.reference import DEFAULT_SETTINGS, validate_setting
from app.dwh.targets import TARGETS
from app.etl.db import etl_transaction
from app.etl.notify import Notification
from app.etl.zakupki import codes
from tests.etl_helpers import (
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)

NORMS = {"eshop": 15, "contest": 40, "tender": 70, "exchange": 20, "direct": 12, "other": 40}


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def test_s4_settings_defaults() -> None:
    assert DEFAULT_SETTINGS["zakupki.method_norms"] == NORMS == codes.DEFAULT_METHOD_NORMS
    assert DEFAULT_SETTINGS["hr.orgs"] == []
    assert "hr.breakdown_path" not in DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["hr.base_url"] == "https://hr-api.uzgidro.uz"
    assert DEFAULT_SETTINGS["hr.attendance_cron"] == "*/10 7-20 * * *"
    for key, cron in (("etl.hr_cron", "30 6 * * *"), ("etl.onec_zakupki_cron", "40 2 * * *")):
        assert DEFAULT_SETTINGS[key] == cron and validate_setting(key, cron) == cron
    assert set(codes.METHOD_TITLES) == {*codes.METHODS, codes.PLAN_METHOD}
    assert codes.STATUSES == ("объявлен", "на оценке", "договор заключён", "отменён", "план")


def test_s4_settings_validation() -> None:
    orgs = [{"org": "Чорвоқ ГЭС", "branch_code": "UGE-02"},
            {"org": "Фарҳод ГЭС", "branch_code": "UGE-05"}]
    assert validate_setting("hr.orgs", orgs) == orgs
    with_id = [{"org": "Чирчик", "branch_code": "UGE-03", "hr_id": 7}]
    assert validate_setting("hr.orgs", with_id) == with_id
    assert validate_setting("zakupki.method_norms", {**NORMS, "tender": 60})["tender"] == 60
    bad: list[tuple[str, Any]] = [
        ("zakupki.method_norms", {k: v for k, v in NORMS.items() if k != "direct"}),
        ("zakupki.method_norms", {**NORMS, "auction": 10}),
        ("zakupki.method_norms", {**NORMS, "eshop": 0}),
        ("zakupki.method_norms", {**NORMS, "eshop": "15"}),
        ("hr.orgs", [*orgs, {"org": "  чорвоқ   гэс ", "branch_code": "UGE-03"}]),
        ("hr.orgs", [{"org": "", "branch_code": "UGE-02"}]),
        ("hr.orgs", [{"org": "X", "branch_code": "UGE-02", "extra": 1}]),
        ("hr.orgs", [*with_id, {"org": "Другой", "branch_code": "UGE-04", "hr_id": 7}]),
        ("hr.orgs", [{"org": "X", "branch_code": "UGE-02", "hr_id": 0}]),
        ("hr.orgs", [{"org": "X", "branch_code": "UGE-02", "hr_id": "7"}]),
        ("hr.attendance_cron", "often"),
        ("etl.hr_cron", "daily"),
    ]
    for key, value in bad:
        with pytest.raises(ValueError):
            validate_setting(key, value)


def test_s4_config_and_notification_kind() -> None:
    assert get_settings().hr_ca_file == "/run/secrets/hr_ca_bundle"
    assert "hr_username" not in Settings.model_fields and "hr_password" not in Settings.model_fields
    assert Notification("hr_rows_rejected", "s", "b").kind == "hr_rows_rejected"


def test_hr_integration_registered() -> None:
    integ = INTEGRATIONS["hr"]
    assert integ.endpoint == ("hr.base_url",)
    assert integ.fields == ("hr.base_url",)
    assert {s.name: s.title for s in integ.secrets} == {"hr.api_key": "API-ключ HR"}
    for key in integ.fields:
        d = REGISTRY[key]
        assert d.category == "integrations" and d.perm == Perm.ADMIN_INTEGRATIONS and d.guarded
    assert validate_setting("hr.base_url", "https://hr.test:8443/api") == "https://hr.test:8443/api"
    assert validate_setting("hr.base_url", "") == ""
    for bad in ("http://hr.test", "https://hr test", "ftp://x"):
        with pytest.raises(ValueError):
            validate_setting("hr.base_url", bad)


def test_targets_forward_and_stage_table() -> None:
    assert TARGETS["fact_investment"].forward and TARGETS["fact_object_stage"].forward
    assert not TARGETS["fact_procurement"].forward and not TARGETS["fact_hr"].forward
    with etl_transaction() as conn:
        row = conn.execute(text(
            "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'dwh' AND c.relname = 'fact_object_stage'")).one()
    assert row.relrowsecurity and row.relforcerowsecurity


def _lot(status: str, method: str) -> dict[str, Any]:
    return {"d": 20260810, "s": "test_s4_ck", "st": status, "m": method}


@pytest.mark.parametrize(("status", "method"), [("в работе", "eshop"), ("объявлен", "auction")])
def test_procurement_checks_reject_unknown_codes(status: str, method: str) -> None:
    with pytest.raises(IntegrityError), etl_transaction() as conn:
        conn.execute(text(
            "INSERT INTO dwh.fact_procurement (date_id, branch_id, lot_no, method, status, "
            "start_price, load_id, src_system, doc_type, src_id) "
            "VALUES (:d, 2, 'L-1', :m, :st, 10, 0, :s, 'portal_lot', 'ck-1')"),
            _lot(status, method))


def test_stage_rows_merge_with_future_dates(source: str) -> None:
    tag = new_tag()
    branch = branch_row(tag)
    obj = {"code": f"O-{tag}", "name": "Тестовый объект", "program_code": None,
           "work_type": "new", "commissioning_year": 2027, "total_cost": 100,
           "source_code": None}

    def stage_row(n: int, day: int, fact: int | None) -> dict[str, Any]:
        return {"doc_type": "aip_stage", "src_id": f"S-{tag}-{n}", "date_id": day,
                "branch_code": branch["code"], "object_code": obj["code"], "stage_no": n,
                "stage_name": f"Этап {n}", "fact_date_id": fact}

    run = open_run(source)
    stage(run, source, {"dim_branch": [branch], "dim_object": [obj],
                        "fact_object_stage": [stage_row(1, 20260315, 20260320),
                                              stage_row(2, 20271215, None)]})
    merge_all(run, source, complete={"fact_object_stage"})
    with etl_transaction() as conn:
        got = conn.execute(text(
            "SELECT stage_no, date_id, fact_date_id FROM dwh.fact_object_stage "
            "WHERE src_system = :s ORDER BY stage_no"), {"s": source}).all()
    assert [tuple(r) for r in got] == [(1, 20260315, 20260320), (2, 20271215, None)]


def test_documented_hr_orgs_example_is_valid() -> None:
    import json

    from tests.ops.repo import repo_path

    path = repo_path("docs/integration/hr-orgs.example.json")
    value = validate_setting("hr.orgs", json.loads(path.read_text(encoding="utf-8")))
    assert {o["hr_id"]: o["branch_code"] for o in value} == {
        1: "UGE-01", 6: "UGE-02", 7: "UGE-03", 8: "UGE-07", 9: "UGE-09", 10: "UGE-12",
        11: "UGE-05", 12: "UGE-10", 13: "UGE-14", 14: "UGE-04", 15: "UGE-06", 16: "UGE-13",
        17: "UGE-16", 18: "UGE-15"}
