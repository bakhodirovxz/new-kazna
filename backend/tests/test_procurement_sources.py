import json
from collections.abc import Iterator, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from app.core.config import ConfigError, get_settings
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.keys import stable_code
from app.etl.runner import Runner
from app.etl.types import HealthResult, Mode, Window
from app.etl.zakupki import codes
from app.etl.zakupki.connector import ProcurementConnector
from app.etl.zakupki.portal import PortalLot, PortalNotConfigured, XaridPortal, method_code
from tests.etl_helpers import (
    TEST_AS_OF,
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)

SEPT = Window(date(2026, 9, 1), TEST_AS_OF)


class ReportSink:
    def __init__(self) -> None:
        self.load_id = 0
        self.rows: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[tuple[str, str, str, str]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None:
        self.errors.append((target, code, message, severity))


class ListPortal:
    name = "list"

    def __init__(self, *lots: PortalLot) -> None:
        self._lots = lots

    def healthcheck(self) -> HealthResult:
        return HealthResult(True, "list")

    def lots(self, window: Window) -> Iterator[PortalLot]:
        yield from self._lots


def _lot(no: str, **kw: Any) -> PortalLot:
    base: dict[str, Any] = {
        "lot_no": no, "customer_inn": "201100002", "method": "Электронный магазин",
        "status": "Объявлен", "announce_date": date(2026, 9, 1), "contract_date": None,
        "start_price_uzs": Decimal("120000000"), "contract_price_uzs": None,
        "supplier_inn": None, "supplier_name": None, "subject": "Запасные части"}
    return PortalLot(**{**base, **kw})


def _extract(*lots: PortalLot) -> ReportSink:
    sink = ReportSink()
    ProcurementConnector(ListPortal(*lots), {"201100002": "UGE-02"}).extract(SEPT, sink)
    return sink


def test_portal_lots_are_mapped_to_canonical_rows() -> None:
    sink = _extract(
        _lot("X-1", status="Заключен договор", contract_date=date(2026, 9, 10),
             contract_price_uzs=Decimal("100000000"), supplier_inn="305555555",
             supplier_name="ООО «Альфа»"),
        _lot("X-2", method="Прямой договор", status="Договор заключён",
             announce_date=date(2026, 9, 5), contract_date=date(2026, 9, 6),
             contract_price_uzs=Decimal("50000000"), supplier_inn="12345678901234",
             supplier_name="Иванов Иван Иванович"),
        _lot("X-3", method="Аукцион", announce_date=date(2026, 9, 15)),
        _lot("X-4", customer_inn="999999999"),
        _lot("X-5", status="Приостановлен"),
        _lot("X-6", status="Договор заключён"),
        _lot("X-7", announce_date=date(2026, 7, 1)),
    )
    facts = {r["src_id"]: r for t, r in sink.rows if t == "fact_procurement"}
    assert set(facts) == {"X-1", "X-2", "X-3"}
    x1, x2, x3 = facts["X-1"], facts["X-2"], facts["X-3"]
    assert (x1["status"], x1["method"], x1["date_id"], x1["procedure_days"]) == (
        codes.DONE, "eshop", 20260910, 9)
    assert (x1["start_price"], x1["contract_price"], x1["branch_code"]) == (
        Decimal("120.00"), Decimal("100.00"), "UGE-02")
    assert x1["cp_code"] == stable_code("XR-CP-", "305555555")
    assert x2["cp_code"] == codes.INDIVIDUAL_CP and x2["method"] == "direct"
    assert (x3["method"], x3["status"], x3["cp_code"], x3["date_id"]) == (
        "other", codes.IN_WORK[0], None, 20260915)
    cps = {r["code"]: r for t, r in sink.rows if t == "dim_counterparty"}
    assert cps[codes.INDIVIDUAL_CP]["name"] == codes.INDIVIDUAL_NAME
    assert cps[codes.INDIVIDUAL_CP]["inn"] is None
    assert "Иванов" not in json.dumps(sink.rows, ensure_ascii=False, default=str)
    assert "Иванов" not in json.dumps(sink.errors, ensure_ascii=False)
    noms = [r for t, r in sink.rows if t == "dim_nomenclature"]
    assert [n["category"] for n in noms] == ["Запасные части"]
    assert [(c, s) for _, c, _, s in sink.errors] == [
        ("unknown_method", "warning"), ("unknown_customer", "error"),
        ("unknown_status", "error"), ("bad_row", "error")]
    assert method_code("  электронный   МАГАЗИН ") == "eshop"


def test_portal_requires_reporting_sink_and_stub_is_not_configured() -> None:
    class Plain:
        def add(self, target: str, row: Mapping[str, Any]) -> None: ...

    with pytest.raises(TypeError):
        ProcurementConnector(ListPortal(), {}).extract(SEPT, Plain())
    with pytest.raises(PortalNotConfigured, match="Портал закупок не настроен"):
        XaridPortal()
    assert "xarid" in set(KNOWN_SOURCES)
    with pytest.raises(ConfigError, match="Портал закупок не настроен"):
        make_connector("xarid", get_settings())


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def test_runner_loads_portal_lots_and_logs_rejections(source: str) -> None:
    tag = new_tag()
    run = open_run(source)
    branch = branch_row(tag, inn="201100777")
    stage(run, source, {"dim_branch": [branch]})
    merge_all(run, source)
    portal = ListPortal(
        _lot("R-1", customer_inn="201100777", status="Договор заключён",
             contract_date=date(2026, 9, 10), contract_price_uzs=Decimal("90000000"),
             supplier_inn="305555555", supplier_name="ООО «Тест»"),
        _lot("R-2", customer_inn="000000000"))
    result = Runner(ProcurementConnector(portal, {"201100777": branch["code"]}, source=source),
                    mode=Mode.FULL, today=TEST_AS_OF, sleep=lambda _: None).run()
    assert result.status in ("success", "failed"), result
    with etl_transaction() as conn:
        codes_logged = conn.execute(text(
            "SELECT code, severity FROM core.etl_error WHERE run_id = :r"),
            {"r": result.run_id}).all()
        rows = conn.execute(text("SELECT count(*) FROM dwh.fact_procurement WHERE src_system = :s"),
                            {"s": source}).scalar_one()
    assert [(c, s) for c, s in codes_logged] == [("unknown_customer", "error")]
    assert rows == 1
