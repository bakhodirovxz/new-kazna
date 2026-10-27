from typing import Any

import pytest
import yaml

from tests.ops.repo import repo_path

DOCS = {
    "docs/integration/banks-format.md": ("row_type", "OB", "CB", "accepted", "executed",
                                         "rejected", "UTF-8", "ГГГГ-ММ-ДД"),
    "docs/integration/banks-connector.md": ("bank-accounts", "banks.statement_branches",
                                            "bank-files", "/srv/ugekazna/banks", "DirectBank"),
    "docs/integration/cbu-telegram.md": ("cbu.enabled", "cbu-backfill", "EGRESS_PROXY",
                                         "telegram-test", "telegram.chat_ids", "Интеграции"),
    "docs/integration/kredity-fayl.md": ("dim_loan.csv", "fact_loan_schedule.csv", "etl-run",
                                         "balance"),
}


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(repo_path("deploy/compose.prod.yml").read_text(encoding="utf-8"))


def test_bank_volumes(compose: dict[str, Any]) -> None:
    worker = compose["services"]["worker"]
    assert "bank_inbox:/data/import/banks:ro" in worker["volumes"]
    assert "bank_archive:/data/archive/banks" in worker["volumes"]
    for name, default in (("bank_inbox", "/srv/ugekazna/banks/inbox"),
                          ("bank_archive", "/srv/ugekazna/banks/archive")):
        opts = compose["volumes"][name]["driver_opts"]
        assert (opts["type"], opts["o"]) == ("none", "bind")
        assert default in opts["device"]
    for service, svc in compose["services"].items():
        if service != "worker":
            assert not any("bank_" in v for v in svc.get("volumes", [])), service


def test_no_integration_credentials_in_compose(compose: dict[str, Any]) -> None:
    # U6/U10: Telegram tokeni/chat'lar va ЦБ - faqat panel (integrations); Docker secret yo'q.
    assert not {s for s in compose["secrets"] if "telegram" in s or "cbu" in s}
    env = compose["services"]["worker"]["environment"]
    assert env["EGRESS_PROXY"] == "${EGRESS_PROXY:-}"
    assert not any("TELEGRAM" in key or "CBU" in key for key in env)
    assert "egress" in compose["services"]["worker"]["networks"]


def test_docs_mention_required_facts() -> None:
    for path, needles in DOCS.items():
        content = repo_path(path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in content, (path, needle)
    hardening = repo_path("docs/ops/host-hardening.md").read_text(encoding="utf-8")
    assert "api.telegram.org" in hardening and "cbu.uz" in hardening
