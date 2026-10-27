from typing import Any

import pytest
import yaml

from tests.ops.repo import repo_path

DOCS = {
    "docs/integration/askue-format.md": (
        "station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours", "UTF-8",
        "ГГГГ-ММ-ДД", "МВт·ч", "unknown_station", "CHARVAK-1;2026-09-22;4810.6"),
    "docs/integration/askue-connector.md": (
        "askue-stations", "/srv/ugekazna/askue/inbox", "askue-live-check", "askue.live_url",
        "askue.live_stale_minutes", "askue.inbox_days", "Интеграции", "install -d"),
    "docs/integration/proizvodstvo-fayl.md": (
        "fact_generation.csv", "generation_plan", "fact_energy_sales.csv", "etl-run",
        "dim_counterparty.csv"),
    "docs/integration/1c-sorov-s3.md": (
        "/materials", "nomenclature_code", "warehouse_name", "min_qty", "last_move_date",
        "debit_sum", "credit_sum", "HTTPS", "Интеграции"),
}


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(repo_path("deploy/compose.prod.yml").read_text(encoding="utf-8"))


def test_askue_inbox_volume(compose: dict[str, Any]) -> None:
    worker = compose["services"]["worker"]
    assert "askue_inbox:/data/import/askue:ro" in worker["volumes"]
    # I2: nomli hajm, host bind YO'Q (katalog bo'lmasa worker ishga tushmay qolardi)
    assert not (compose["volumes"]["askue_inbox"] or {}).get("driver_opts")
    for service, svc in compose["services"].items():
        if service != "worker":
            assert not any("askue" in v for v in svc.get("volumes", [])), service


def test_no_s3_credentials_in_compose_or_env(compose: dict[str, Any]) -> None:
    """U6/U10: treplex va 1C-ombor manzili/hisobi faqat panelda — Docker secret/env yo'q."""
    assert not [s for s in compose["secrets"] if s.startswith("onec_sklad")]
    for service, svc in compose["services"].items():
        env = svc.get("environment", {})
        assert "ASKUE_LIVE_URL" not in env and "ONEC_SKLAD_BASE_URL" not in env, service


def test_docs_mention_required_facts() -> None:
    for path, needles in DOCS.items():
        content = repo_path(path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in content, (path, needle)
        assert "ASKUE_LIVE_URL" not in content and "onec_sklad_password" not in content, path
    hardening = repo_path("docs/ops/host-hardening.md").read_text(encoding="utf-8")
    assert "treplex.uz" in hardening and "askue.live_url" in hardening
