from typing import Any

import pytest
import yaml

from tests.ops.repo import repo_path

HR = {"hr_username", "hr_password"}  # U10: HR hisobi Docker secret emas — panel (integrations)
DOCS = {
    "docs/integration/zakupki-format.md": (
        "fact_procurement.csv", "договор заключён", "на оценке", "eshop", "direct",
        "zakupki.method_norms", "procurement_plan", "CP-FL", "UTF-8"),
    "docs/integration/aip-format.md": (
        "fact_investment.csv", "fact_object_stage.csv", "dim_object.csv", "aip_opening",
        "physical_pct", "advance_date_id", "adreska", "responsible_person"),
    "docs/integration/kadry-fayl.md": (
        "fact_hr.csv", "dim_position.csv", "headcount_plan", "overtime_hours",
        "kazna.calendar_kinds", "ФИО"),
    "docs/integration/hr-connector.md": (
        "hr.base_url", "hr.username", "hr-orgs", "hr-check", "extra_hosts",
        "hr.breakdown_path", "no_branch_breakdown"),
    "docs/integration/hr-sorov-s4.md": (
        "organization", "staff_units", "hired", "fired", "overtime_hours",
        "персональных данных", "только чтение"),
    "docs/integration/1c-sorov-s4.md": (
        "/purchasePlan", "org_uid", "purchase_method_name", "/purchaseRequests",
        "responsible_name", "КС-2"),
}


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(repo_path("deploy/compose.prod.yml").read_text(encoding="utf-8"))


def test_hr_credentials_are_not_docker_secrets_or_env(compose: dict[str, Any]) -> None:
    assert not (HR & set(compose["secrets"]))
    for service, svc in compose["services"].items():
        assert not (HR & set(svc.get("secrets", []))), service
        assert "HR_BASE_URL" not in svc.get("environment", {}), service


def test_docs_mention_required_facts() -> None:
    for path, needles in DOCS.items():
        content = repo_path(path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in content, (path, needle)
    hardening = repo_path("docs/ops/host-hardening.md").read_text(encoding="utf-8")
    assert "hr-api.uzgidro.uz" in hardening
