"""Deny-by-default route himoyasi to'liqligini tekshiradi.

NB (fix r1 / I5): o'rnatilgan FastAPI (0.141.x) `include_router()`ni endi DARHOL
`app.routes`ga yozmaydi — har bir chaqiruv `fastapi.routing._IncludedRouter` degan "dangasa"
o'ramga aylanadi, u faqat `.effective_candidates()` chaqirilganda (masalan, haqiqiy so'rov
kelganda) o'z ichidagi marshrutlarni HAR SAFAR to'liq (prefiks + birlashtirilgan
dependency'lar bilan) hisoblab beradi. Shuning uchun bu yerda `create_app().routes`ni
NAIV `isinstance(route, APIRoute)` bilan emas, balki shu `_IncludedRouter` mexanizmini
rekursiv "yoyib" (`_resolve`) chin marshrut jadvalini olamiz — aks holda quyidagi barcha
testlar aslida BO'SH ro'yxat ustida yurib, sinovsiz "passed" bo'lib qolar edi (I5ning aynan
o'zi izlagan bo'shliq turi)."""

from __future__ import annotations

from collections.abc import Iterator

import fastapi.routing as fastapi_routing
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import BaseRoute

from app.auth.context import get_ctx
from app.main import create_app

PUBLIC = {
    ("GET", "/api/v1/healthz"),
    ("GET", "/api/v1/readyz"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/2fa/verify"),
    ("POST", "/api/v1/auth/2fa/enroll/start"),
    ("POST", "/api/v1/auth/2fa/enroll/confirm"),
    ("POST", "/api/v1/auth/logout"),
}
# I5 (fix r1): ("GET", "/api/v1/openapi.json") olib tashlandi — `openapi_url=None` bo'lgani
# uchun bu route hozircha umuman mavjud emas (Task 13'da qo'shiladi va PUBLIC'ga qaytariladi).
PREFIX_PERMS = {"/api/v1/admin": "admin:", "/api/v1/audit": "audit:read"}
# I5: `app.routes`dagi har bir TOP-LEVEL yozuv yoki `APIRoute` (to'g'ridan-to'g'ri qo'shilgan
# bo'lsa), yoki `_IncludedRouter` (`include_router()` orqali) bo'lishi kerak — boshqa turdagi
# route (masalan, qo'lda qo'shilgan `Mount`/`WebSocketRoute`) shu ro'yxatga aniq kiritilishi
# shart, aks holda test yiqiladi. Hozircha bo'sh.
NON_STANDARD_ROUTE_ALLOWLIST: set[str] = set()


def _resolve(route: BaseRoute) -> Iterator[object]:
    """`_IncludedRouter`larni rekursiv yoyib, chin (to'liq prefiksli, dependency'lari
    birlashtirilgan) `_EffectiveRouteContext` obyektlarini beradi."""
    if isinstance(route, fastapi_routing._IncludedRouter):
        for candidate in route.effective_candidates():
            yield from _resolve(candidate)
    else:
        yield route


def _calls(dep: Dependant) -> Iterator[object]:
    for sub in dep.dependencies:
        yield sub.call
        yield from _calls(sub)


def _routes() -> Iterator[tuple[str, str, Dependant]]:
    """(HTTP metod, to'liq yo'l, shu marshrutning to'liq — prefiks-darajasidagi
    dependency'lar bilan birlashtirilgan — `Dependant`i)."""
    for top in create_app().routes:
        for ctx in _resolve(top):
            for method in ctx.methods:
                yield method, ctx.path, ctx.dependant


def _matches_prefix(path: str, prefix: str) -> bool:
    """I5: `"/api/v1/admin"` prefiksi `"/api/v1/adminfoo"`ga emas, faqat aynan o'ziga yoki
    `"/api/v1/admin/..."`ga mos kelishi kerak."""
    return path == prefix or path.startswith(prefix + "/")


def test_every_route_is_standard() -> None:
    for route in create_app().routes:
        if isinstance(route, APIRoute | fastapi_routing._IncludedRouter):
            continue
        path = getattr(route, "path", repr(route))
        assert path in NON_STANDARD_ROUTE_ALLOWLIST, f"kutilmagan turdagi route: {route!r}"


def test_public_routes_correspond_to_existing_routes() -> None:
    existing = {(method, path) for method, path, _ in _routes()}
    for entry in PUBLIC:
        assert entry in existing, f"PUBLIC yozuvi {entry} hech qanday route'ga mos kelmaydi"


def test_every_non_public_route_requires_session() -> None:
    for method, path, dependant in _routes():
        if (method, path) in PUBLIC:
            continue
        assert get_ctx in set(_calls(dependant)), f"{method} {path} himoyasiz"


def test_admin_and_audit_routes_require_matching_permission() -> None:
    for method, path, dependant in _routes():
        for prefix, needed in PREFIX_PERMS.items():
            if not _matches_prefix(path, prefix):
                continue
            perms: set[str] = set()
            for call in _calls(dependant):
                perms |= set(getattr(call, "required_perms", ()))
            assert any(p.startswith(needed) for p in perms), f"{method} {path}: {perms}"


def test_all_protected_routes_return_401_without_session() -> None:
    with TestClient(create_app(), base_url="https://testserver") as client:
        for method, path, _dependant in _routes():
            if (method, path) in PUBLIC:
                continue
            req_path = path.replace("{user_id}", "1").replace("{role_id}", "1").replace(
                "{position_id}", "1").replace("{session_id}", "00000000-0000-0000-0000-000000000000"
            ).replace("{purpose}", "mfa")
            response = client.request(method, req_path, json={})
            assert response.status_code == 401, f"{method} {req_path}: {response.status_code}"
