from collections.abc import Iterator

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.auth.context import get_ctx
from app.main import create_app

PUBLIC = {
    ("GET", "/api/v1/healthz"),
    ("GET", "/api/v1/readyz"),
    ("GET", "/api/v1/openapi.json"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/2fa/verify"),
    ("POST", "/api/v1/auth/2fa/enroll/start"),
    ("POST", "/api/v1/auth/2fa/enroll/confirm"),
    ("POST", "/api/v1/auth/logout"),
}
PREFIX_PERMS = {"/api/v1/admin/": "admin:", "/api/v1/audit": "audit:read"}


def _calls(dep: Dependant) -> Iterator[object]:
    for sub in dep.dependencies:
        yield sub.call
        yield from _calls(sub)


def _routes() -> Iterator[tuple[str, APIRoute]]:
    for route in create_app().routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                yield method, route


def test_every_non_public_route_requires_session() -> None:
    for method, route in _routes():
        if (method, route.path) in PUBLIC:
            continue
        assert get_ctx in set(_calls(route.dependant)), f"{method} {route.path} himoyasiz"


def test_admin_and_audit_routes_require_matching_permission() -> None:
    for method, route in _routes():
        for prefix, needed in PREFIX_PERMS.items():
            if not route.path.startswith(prefix):
                continue
            perms: set[str] = set()
            for call in _calls(route.dependant):
                perms |= set(getattr(call, "required_perms", ()))
            assert any(p.startswith(needed) for p in perms), f"{method} {route.path}: {perms}"


def test_all_protected_routes_return_401_without_session() -> None:
    with TestClient(create_app(), base_url="https://testserver") as client:
        for method, route in _routes():
            if (method, route.path) in PUBLIC:
                continue
            path = route.path.replace("{user_id}", "1").replace("{role_id}", "1").replace(
                "{position_id}", "1").replace("{session_id}", "00000000-0000-0000-0000-000000000000"
            ).replace("{purpose}", "mfa")
            response = client.request(method, path, json={})
            assert response.status_code == 401, f"{method} {path}: {response.status_code}"
