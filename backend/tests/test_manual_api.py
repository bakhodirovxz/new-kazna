import json
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.auth.context import CSRF_HEADER
from app.main import create_app
from tests.helpers import SeedUser, login
from tests.manual_helpers import (
    audit_dump,
    audit_rows,
    balance_item,
    bank_account_item,
    branch_code,
    migrator_sql,
    seed_dwh_bank,
)

pytestmark = pytest.mark.usefixtures("clean_manual")
MakeUser = Callable[..., SeedUser]
BANK = "BA-t7bank0000000001"


@pytest.fixture
def client_for() -> Iterator[Callable[[SeedUser], TestClient]]:
    opened: list[TestClient] = []

    def make(user: SeedUser) -> TestClient:
        client = TestClient(create_app(), base_url="https://testserver")
        client.__enter__()
        opened.append(client)
        return login(client, user)

    seed_dwh_bank(BANK)
    yield make
    for client in opened:
        client.__exit__(None, None, None)


def _body(entity: str, items: list[dict], *, submit: bool = False, branch_id: int = 1) -> dict:  # type: ignore[type-arg]
    return {"entity": entity, "branch_id": branch_id, "origin": "form", "submit": submit,
            "items": [{"values": v} for v in items]}


def test_entities_filtered_by_perms(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    econ = client_for(make_user("economist_filiala", branch_ids=(2,)))
    ents = {e["id"]: e for e in econ.get("/api/v1/data/entities").json()}
    assert {"kazna.balance", "kazna.bank_account", "kazna.payment_plan"} <= set(ents)
    assert ents["kazna.balance"]["can_write"] and not ents["kazna.balance"]["can_approve"]
    assert {f["name"] for f in ents["kazna.balance"]["fields"]} == {
        "branch_code", "bank_code", "date", "balance"}
    boss = client_for(make_user("nach_otdela"))
    assert next(e for e in boss.get("/api/v1/data/entities").json()
                if e["id"] == "kazna.balance")["can_approve"]


def test_full_form_flow_http(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    checker = client_for(make_user("nach_otdela"))
    r = maker.post("/api/v1/data/batches",
                   json=_body("kazna.balance", [balance_item(BANK, "2026-09-30", "1500.00")],
                              submit=True))
    assert r.status_code == 201, r.text
    batch = r.json()
    assert batch["status"] == "submitted"
    inbox = checker.get("/api/v1/data/batches?box=inbox").json()
    assert [b["batch_id"] for b in inbox["items"]] == [batch["batch_id"]]
    assert maker.get("/api/v1/data/batches?box=mine").json()["total"] == 1
    detail = checker.get(f"/api/v1/data/batches/{batch['batch_id']}").json()
    assert detail["items"][0]["op"] == "add" and detail["publication"]["status"] == "none"
    r = checker.post(f"/api/v1/data/batches/{batch['batch_id']}/approve",
                     json={"expected_version": batch["version"]})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    detail = checker.get(f"/api/v1/data/batches/{batch['batch_id']}").json()
    assert detail["publication"]["status"] == "queued"
    recs = maker.get("/api/v1/data/entities/kazna.balance/records?per=ytd").json()
    assert recs["total"] == 1 and recs["items"][0]["status"] == "active"
    assert recs["items"][0]["values"]["balance"] == "1500.00"
    hist = maker.get(f"/api/v1/data/records/{recs['items'][0]['entry_id']}/history").json()
    assert hist["versions"][0]["batch_status"] == "approved"


def test_self_approval_forbidden_api(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    from tests.manual_helpers import make_role_user

    both = client_for(make_role_user({"data:kazna:write", "data:kazna:approve"},
                                     scope_all=True))
    batch = both.post("/api/v1/data/batches", json=_body(
        "kazna.balance", [balance_item(BANK, "2026-09-30", "1.00")], submit=True)).json()
    r = both.post(f"/api/v1/data/batches/{batch['batch_id']}/approve",
                  json={"expected_version": batch["version"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval_forbidden"
    denied = [a for a in audit_rows("data.batch.approved") if a["result"] == "denied"]
    assert denied


def test_foreign_branch_is_403_and_audited(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    econ = client_for(make_user("economist_filiala", branch_ids=(2,)))
    r = econ.post("/api/v1/data/batches", json=_body(
        "kazna.balance", [balance_item(BANK, "2026-09-30", "1.00", branch_id=3)], branch_id=3))
    assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation"
    assert audit_rows("security.rls_violation_attempt")
    assert migrator_sql("SELECT count(*) FROM core.manual_batch")[0][0] == 0


def test_foreign_branch_batch_invisible(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    batch = maker.post("/api/v1/data/batches", json=_body(
        "kazna.balance", [balance_item(BANK, "2026-09-30", "1.00", branch_id=3)],
        branch_id=3)).json()
    econ = client_for(make_user("economist_filiala", branch_ids=(2,)))
    assert econ.get(f"/api/v1/data/batches/{batch['batch_id']}").status_code == 404
    assert econ.get("/api/v1/data/batches?box=mine").json()["total"] == 0


def test_csrf_required(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    maker.headers.pop(CSRF_HEADER)
    r = maker.post("/api/v1/data/batches", json=_body(
        "kazna.balance", [balance_item(BANK, "2026-09-30", "1.00")]))
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"


def test_items_limit_500_and_extra_fields(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    item = balance_item(BANK, "2026-09-30", "1.00")
    assert maker.post("/api/v1/data/batches",
                      json=_body("kazna.balance", [item] * 501)).status_code == 422
    body = _body("kazna.balance", [item])
    body["status"] = "approved"  # mass-assignment
    assert maker.post("/api/v1/data/batches", json=body).status_code == 422


def test_conflict_and_validation_http(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    bad = balance_item(BANK, "2026-09-30", "1.005")
    r = maker.post("/api/v1/data/batches", json=_body("kazna.balance", [bad]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_value"
    assert r.json()["error"]["params"]["fields"] == ["balance"]
    ok = maker.post("/api/v1/data/batches", json=_body(
        "kazna.balance", [balance_item(BANK, "2026-09-30", "1.00")])).json()
    r = maker.post(f"/api/v1/data/batches/{ok['batch_id']}/submit",
                   json={"expected_version": ok["version"] + 5})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict_modified"


def test_history_masks_secret_and_no_leak(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    checker = client_for(make_user("nach_otdela"))
    plain = "20208000999988887777"
    r = maker.post("/api/v1/data/batches", json=_body(
        "kazna.bank_account", [bank_account_item(number=plain)], submit=True))
    batch = r.json()
    checker.post(f"/api/v1/data/batches/{batch['batch_id']}/approve",
                 json={"expected_version": batch["version"]})
    recs = maker.get("/api/v1/data/entities/kazna.bank_account/records?per=ytd").json()
    eid = recs["items"][0]["entry_id"]
    everything = json.dumps([
        r.json(),
        recs,
        maker.get(f"/api/v1/data/records/{eid}/history").json(),
        checker.get(f"/api/v1/data/batches/{batch['batch_id']}").json(),
        maker.get("/api/v1/data/entities/kazna.balance/options/bank_code").json(),
    ], ensure_ascii=False) + audit_dump()
    for part in (r.json(), recs, maker.get(f"/api/v1/data/records/{eid}/history").json()):
        assert plain not in json.dumps(part)
    assert plain not in audit_dump()
    assert plain not in everything and "…7777" in everything
    opts = maker.get("/api/v1/data/entities/kazna.balance/options/bank_code?q=7777").json()
    assert opts and opts[0]["code"].startswith("BA-")


def test_options_filter_and_like_escaping(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    codes = [o["code"] for o in maker.get(
        "/api/v1/data/entities/kazna.balance/options/bank_code?q=t7bank").json()]
    assert codes == [BANK]
    assert maker.get("/api/v1/data/entities/kazna.balance/options/bank_code?q=%25").json() == []
    items = maker.get("/api/v1/data/entities/kazna.payment_plan/options/item_code").json()
    assert items and all(i["code"] != "PKM54-I06" for i in items)  # faqat chiquvchi
    assert maker.get("/api/v1/data/entities/kazna.balance/options/balance").status_code == 404
    assert branch_code(1)


def test_options_respect_rls(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    checker = client_for(make_user("nach_otdela"))
    b = maker.post("/api/v1/data/batches", json=_body(
        "kazna.bank_account", [bank_account_item(3, number="20208000555500001111")],
        submit=True, branch_id=3)).json()
    checker.post(f"/api/v1/data/batches/{b['batch_id']}/approve",
                 json={"expected_version": b["version"]})
    econ = client_for(make_user("economist_filiala", branch_ids=(2,)))
    assert econ.get("/api/v1/data/entities/kazna.balance/options/bank_code?q=1111").json() == []
    assert maker.get("/api/v1/data/entities/kazna.balance/options/bank_code?q=1111").json()


def test_no_perm_403(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    viewer = client_for(make_user("profil_sluzhba"))
    assert viewer.get("/api/v1/data/entities").status_code == 403
    assert viewer.post("/api/v1/data/batches", json=_body(
        "kazna.balance", [balance_item(BANK, "2026-09-30", "1")])).status_code == 403
    admin = client_for(make_user("admin"))
    assert admin.get("/api/v1/data/entities").json() == []  # SoD: admin data:* olmaydi
    assert admin.post("/api/v1/data/batches", json=_body(
        "kazna.balance", [balance_item(BANK, "2026-09-30", "1")])).status_code == 403
    auditor = client_for(make_user("vnutr_kontrol"))
    assert auditor.get("/api/v1/data/entities").json() == []
    assert auditor.get("/api/v1/data/entities/kazna.balance/records").status_code == 403


def test_auditor_reads_history(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    b = maker.post("/api/v1/data/batches", json=_body(
        "kazna.balance", [balance_item(BANK, "2026-09-30", "1.00")], submit=True)).json()
    eid = migrator_sql("SELECT entry_id FROM core.manual_entry WHERE batch_id = :b",
                       b=b["batch_id"])[0][0]
    auditor = client_for(make_user("vnutr_kontrol"))
    assert auditor.get(f"/api/v1/data/records/{eid}/history").status_code == 200
    viewer = client_for(make_user("profil_sluzhba"))
    assert viewer.get(f"/api/v1/data/records/{eid}/history").status_code == 403


def test_route_guards_cover_data_router() -> None:
    from app.auth.permissions import ALL_DATA_PERMS
    from tests.test_route_guards import _calls, _routes

    seen = 0
    for _method, path, dep in _routes():
        if not path.startswith("/api/v1/data"):
            continue
        seen += 1
        perms: set[str] = set()
        for call in _calls(dep):
            perms |= set(getattr(call, "required_perms", ()))
        assert set(ALL_DATA_PERMS) <= perms and "audit:read" in perms, path
    assert seen == 15


def test_approved_batch_diff_relative_to_prior(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    checker = client_for(make_user("nach_otdela"))

    def run(items: list[dict], **extra) -> dict:  # type: ignore[type-arg]
        body = _body("kazna.balance", [balance_item(BANK, "2026-09-30", "1.00")], submit=True)
        body["items"] = items
        batch = maker.post("/api/v1/data/batches", json=body | extra).json()
        r = checker.post(f"/api/v1/data/batches/{batch['batch_id']}/approve",
                         json={"expected_version": batch["version"]})
        assert r.status_code == 200, (r.text, batch)
        return checker.get(f"/api/v1/data/batches/{batch['batch_id']}").json()

    first = run([{"values": balance_item(BANK, "2026-09-30", "1500.00")}])
    assert [(c["op"], c["before"]) for c in first["items"]] == [("add", None)]
    entry_id = first["items"][0]["entry_id"]
    second = run([{"entry_id": entry_id, "expected_version": 1, "values": balance_item(
        BANK, "2026-09-30", "1700.00")}], reason="korrektirovka")
    (change,) = second["items"]
    assert change["op"] == "change"
    assert change["before"]["balance"] == "1500.00" and change["after"]["balance"] == "1700.00"
    again = checker.get(f"/api/v1/data/batches/{first['batch_id']}").json()
    assert again["items"][0]["op"] == "add"
