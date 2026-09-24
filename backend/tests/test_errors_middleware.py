import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import ConflictError, RateLimitedError
from app.main import create_app


class Body(BaseModel):
    secret_value: str
    amount: int


def _app() -> FastAPI:
    app = create_app()

    @app.get("/api/v1/_t/conflict")
    def conflict() -> None:
        raise ConflictError("username_taken")

    @app.get("/api/v1/_t/limited")
    def limited() -> None:
        raise RateLimitedError(retry_after=42)

    @app.get("/api/v1/_t/boom")
    def boom() -> None:
        raise RuntimeError("DB password is hunter2")

    @app.post("/api/v1/_t/echo")
    def echo(body: Body) -> dict[str, int]:
        return {"amount": body.amount}

    return app


@pytest.fixture
def client() -> TestClient:
    with TestClient(_app(), base_url="https://testserver", raise_server_exceptions=False) as c:
        yield c


def test_app_error_format(client: TestClient) -> None:
    r = client.get("/api/v1/_t/conflict")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "username_taken"
    assert err["message"] == "Логин уже занят"
    assert err["request_id"] == r.headers["X-Request-ID"]


def test_rate_limited_sets_retry_after(client: TestClient) -> None:
    r = client.get("/api/v1/_t/limited")
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "42"
    assert r.json()["error"]["params"] == {"retry_after": 42}


def test_unhandled_error_hides_details(client: TestClient) -> None:
    r = client.get("/api/v1/_t/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in r.text


def test_validation_error_does_not_echo_input(client: TestClient) -> None:
    r = client.post("/api/v1/_t/echo", json={"secret_value": "TOPSECRET", "amount": "abc"})
    assert r.status_code == 422
    assert r.json()["error"]["params"] == {"fields": ["amount"]}
    assert "TOPSECRET" not in r.text


def test_unknown_route_is_formatted_404(client: TestClient) -> None:
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_security_headers_present(client: TestClient) -> None:
    r = client.get("/api/v1/healthz")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["Strict-Transport-Security"].startswith("max-age=")
    assert len(r.headers["X-Request-ID"]) == 32


def test_body_limit_by_content_length(client: TestClient) -> None:
    r = client.post("/api/v1/_t/echo", content=b"x" * 1_100_000,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_lifespan_refuses_bad_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main as main_module

    monkeypatch.setattr(main_module, "get_settings", lambda: Settings(env="test", master_kek="bad"))
    with pytest.raises(Exception, match="master_kek"), TestClient(main_module.create_app()):
        pass
