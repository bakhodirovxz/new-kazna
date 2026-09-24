from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz() -> None:
    with TestClient(create_app(), base_url="https://testserver") as client:
        response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
