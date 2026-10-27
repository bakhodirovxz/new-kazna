from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF
from tests.helpers import SeedUser, login


@pytest.fixture
def client_for() -> Iterator[Callable[[SeedUser], TestClient]]:
    clients: list[TestClient] = []

    def make(user: SeedUser) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return login(client, user)

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def test_synthetic_staff(published_synthetic: int, client_for: Callable[[SeedUser], TestClient],
                         make_user: Callable[..., SeedUser]) -> None:
    client = client_for(make_user("rukovodstvo"))
    body = client.get("/api/v1/kadry/chislennost", params={"per": "m08"}).json()
    synthetic = [b for b in body["branches"] if b["branch_id"] <= 16]
    assert len(synthetic) == 16 and all(b["fact"] <= b["plan"] + 4 for b in synthetic)
    fot = client.get("/api/v1/kadry/fot", params={"per": "m08"}).json()
    assert fot["kpis"]["payroll"] > 0  # PKM54-O05 (sintetik) — standart ФОТ statyasi
