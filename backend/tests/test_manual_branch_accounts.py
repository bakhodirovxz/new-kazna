"""«Ввод данных»: счёт (dim_bank) выбирается только из счетов своего филиала.

Связь счёт <-> филиал: (а) утверждённый ручной «Банковский счёт» этого филиала или (б) остатки
(`dwh.fact_balance`) этого филиала по счёту. Проверка серверная (выбор и импорт: один путь)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ValidationFailed
from app.main import create_app
from app.manual import approval, store
from tests.helpers import SeedUser, login
from tests.manual_helpers import (
    balance_item,
    bank_account_item,
    branch_code,
    ctx_of,
    run,
    seed_dwh_bank,
)

pytestmark = pytest.mark.usefixtures("clean_manual")
MakeUser = Callable[..., SeedUser]
BANK = "BA-brA0000000000001"  # faqat 1-filial qoldiqlarida
OPT = "/api/v1/data/entities/kazna.balance/options/bank_code"


@pytest.fixture
def client_for() -> Iterator[Callable[[SeedUser], TestClient]]:
    opened: list[TestClient] = []

    def make(user: SeedUser) -> TestClient:
        client = TestClient(create_app(), base_url="https://testserver")
        client.__enter__()
        opened.append(client)
        return login(client, user)

    seed_dwh_bank(BANK, branches=(1,))
    yield make
    for client in opened:
        client.__exit__(None, None, None)


def _balance(ctx, code: str, branch: int):  # type: ignore[no-untyped-def]
    return run(ctx, store.create_batch, entity_id="kazna.balance", branch_id=branch,
               origin="form", items=[store.ItemIn(values=balance_item(code, "2026-09-30", "5.00",
                                                                      branch))])


def test_picker_lists_only_accounts_of_the_branch(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    assert BANK in [o["code"] for o in maker.get(f"{OPT}?q=brA&br=1").json()]
    assert maker.get(f"{OPT}?q=brA&br=2").json() == []


def test_server_rejects_account_of_another_branch(make_user: MakeUser) -> None:
    seed_dwh_bank(BANK, branches=(1,))
    maker = ctx_of(make_user("spec_kazna"))
    assert _balance(maker, BANK, 1).status == "draft"
    with pytest.raises(ValidationFailed) as exc:
        _balance(maker, BANK, 2)
    assert exc.value.params["rows"] == [
        {"row": 1, "field": "bank_code", "code": "reference_not_found"}]


def test_manual_account_belongs_to_its_branch(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker, checker = ctx_of(make_user("spec_kazna")), ctx_of(make_user("nach_otdela"))
    b = run(maker, store.create_batch, entity_id="kazna.bank_account", branch_id=3,
            origin="form", items=[store.ItemIn(values=bank_account_item(3))], submit=True)
    run(checker, approval.approve_batch, b.batch_id, expected_version=b.version)
    from tests.manual_helpers import migrator_sql
    acc = str(migrator_sql("SELECT code FROM core.manual_head")[0][0])
    assert _balance(maker, acc, 3).status == "draft"
    with pytest.raises(ValidationFailed):
        _balance(maker, acc, 1)
    http = client_for(make_user("spec_kazna"))
    assert acc in [o["code"] for o in http.get(f"{OPT}?br=3").json()]
    assert acc not in [o["code"] for o in http.get(f"{OPT}?br=1").json()]


def test_import_validates_account_against_the_branch(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    body = (f"branch_code;bank_code;date;balance\r\n{branch_code(2)};{BANK};2026-09-30;1\r\n"
            ).encode()
    r = maker.post("/api/v1/data/entities/kazna.balance/import?branch_id=2", content=body,
                   headers={"Content-Type": "text/csv", "X-File-Name": quote("a.csv")})
    assert r.status_code == 422
    assert r.json()["error"]["params"]["rows"] == [
        {"row": 2, "field": "bank_code", "code": "reference_not_found"}]
