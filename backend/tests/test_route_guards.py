"""Deny-by-default route himoyasi to'liqligini tekshiradi.

NB (fix r1 / I5): o'rnatilgan FastAPI (0.141.x) `include_router()`ni endi DARHOL
`app.routes`ga yozmaydi — har bir chaqiruv `fastapi.routing._IncludedRouter` degan "dangasa"
o'ramga aylanadi, u faqat `.effective_candidates()` chaqirilganda (masalan, haqiqiy so'rov
kelganda) o'z ichidagi marshrutlarni HAR SAFAR to'liq (prefiks + birlashtirilgan
dependency'lar bilan) hisoblab beradi. Shuning uchun bu yerda `create_app().routes`ni
NAIV `isinstance(route, APIRoute)` bilan emas, balki shu `_IncludedRouter` mexanizmini
rekursiv "yoyib" (`_resolve`) chin marshrut jadvalini olamiz — aks holda quyidagi barcha
testlar aslida BO'SH ro'yxat ustida yurib, sinovsiz "passed" bo'lib qolar edi.

NB (fix r2 / R2-1): `_resolve` yoyilgan yakuniy yozuvlarni ENDI QAT'IY tekshiradi — avval
`APIRoute` bo'lmagan (yoki bo'sh `methods`/`None` `dependant`ga ega) yozuvlar shunchaki
"o'tkazib yuborilardi" (`ctx.methods` bo'sh bo'lgani uchun ichki `for method in ctx.methods`
sira ishlamas, demak shu route HECH QACHON hech qanday testda tekshirilmasdi — yana bir
"sinovsiz o'tish" turi). Endi bunday yozuv aniq allowlist'da bo'lmasa, `AssertionError` bilan
yiqiladi (pastda `test_resolve_raises_on_raw_route_inside_included_router` bilan sinaladi)."""

from __future__ import annotations

from collections.abc import Iterator

import fastapi.routing as fastapi_routing
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import BaseRoute
from starlette.routing import Route as StarletteRoute

from app.auth.context import get_ctx, require_perm
from app.core.db import get_db
from app.main import create_app

PUBLIC = {
    ("GET", "/api/v1/healthz"),
    ("GET", "/api/v1/readyz"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/2fa/verify"),
    ("POST", "/api/v1/auth/2fa/enroll/start"),
    ("POST", "/api/v1/auth/2fa/enroll/confirm"),
    ("POST", "/api/v1/auth/logout"),
    # Task 13: `_mount_openapi` bu route'ni faqat `settings.env == "prod"` bo'lsa
    # `admin:settings` bilan himoyalaydi; dev/test'da (shu jumladan shu testlar ishlaydigan
    # muhitda) ochiq — shuning uchun bu yerda PUBLIC.
    ("GET", "/api/v1/openapi.json"),
}
PREFIX_PERMS = {"/api/v1/admin": "admin:", "/api/v1/audit": "audit:read",
                "/api/v1/obzor": "section:obzor:view",
                "/api/v1/kazna": "section:kazna:view",
                "/api/v1/kredity": "section:kredity:view",
                "/api/v1/zakupki": "section:zakupki:view",
                "/api/v1/investicii": "section:investicii:view",
                "/api/v1/kadry": "section:kadry:view",
                "/api/v1/proizvodstvo": "section:proizvodstvo:view",
                "/api/v1/sklad": "section:sklad:view",
                "/api/v1/exports": "export:csv"}
# R2-1: `_resolve` yakuniy yozuvi `APIRoute` bo'lmasa, shu yerda ANIQ ro'yxatga kiritilmagan
# bo'lsa, test yiqiladi. Hozircha bo'sh — hech qanday xom (APIRoute bo'lmagan) route yo'q.
NON_STANDARD_ROUTE_ALLOWLIST: set[str] = set()
# R2-1: joriy ilova uchun aniq kutilgan (HTTP metod, to'liq yo'l) to'plami — yangi yoki
# yo'qolgan marshrut shu ro'yxatni ONGLI ravishda yangilashni talab qiladi.
EXPECTED_ROUTES = frozenset({
    ("DELETE", "/api/v1/auth/sessions/{session_id}"),
    ("GET", "/api/v1/admin/keys"),
    ("POST", "/api/v1/admin/keys/{purpose}/rotate"),
    ("GET", "/api/v1/admin/permissions"),
    ("GET", "/api/v1/ai/status"),
    ("POST", "/api/v1/ai/analyze"),
    ("GET", "/api/v1/audit/ai-requests"),
    ("GET", "/api/v1/audit"),
    ("GET", "/api/v1/audit/export.csv"),
    ("POST", "/api/v1/audit/verify"),
    ("GET", "/api/v1/openapi.json"),
    ("GET", "/api/v1/admin/positions"),
    ("GET", "/api/v1/admin/roles"),
    ("GET", "/api/v1/admin/users"),
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/auth/sessions"),
    ("GET", "/api/v1/healthz"),
    ("GET", "/api/v1/readyz"),
    ("GET", "/api/v1/meta/branches"),
    ("GET", "/api/v1/meta/periods"),
    ("GET", "/api/v1/meta/menu"),
    ("GET", "/api/v1/meta/freshness"),
    ("GET", "/api/v1/kazna/svod"),
    ("GET", "/api/v1/kazna/platezhi"),
    ("GET", "/api/v1/kazna/platezhi/items/{item_id}"),
    ("GET", "/api/v1/kazna/calendar"),
    ("GET", "/api/v1/kazna/dogovory"),
    ("GET", "/api/v1/kazna/celevye"),
    ("GET", "/api/v1/kredity/svod"),
    ("GET", "/api/v1/kredity/reestr"),
    ("GET", "/api/v1/kredity/grafik"),
    ("GET", "/api/v1/zakupki/svod"),
    ("GET", "/api/v1/zakupki/loty"),
    ("GET", "/api/v1/zakupki/postavshiki"),
    ("GET", "/api/v1/zakupki/ekonomiya"),
    ("GET", "/api/v1/investicii/svod"),
    ("GET", "/api/v1/investicii/obekty"),
    ("GET", "/api/v1/investicii/istochniki"),
    ("GET", "/api/v1/investicii/riski"),
    ("GET", "/api/v1/kadry/svod"),
    ("GET", "/api/v1/kadry/chislennost"),
    ("GET", "/api/v1/kadry/fot"),
    ("GET", "/api/v1/kadry/dvizhenie"),
    ("GET", "/api/v1/proizvodstvo/svod"),
    ("GET", "/api/v1/proizvodstvo/stancii"),
    ("GET", "/api/v1/proizvodstvo/realiz"),
    ("GET", "/api/v1/proizvodstvo/moshchnost"),
    ("GET", "/api/v1/sklad/svod"),
    ("GET", "/api/v1/sklad/ostatki"),
    ("GET", "/api/v1/sklad/minimum"),
    ("GET", "/api/v1/sklad/nelikvid"),
    ("GET", "/api/v1/obzor/excel.xlsx"),
    ("POST", "/api/v1/exports/log"),
    ("GET", "/api/v1/obzor/vnimanie"),
    ("GET", "/api/v1/obzor/vnimanie/count"),
    ("GET", "/api/v1/obzor/svod"),
    ("GET", "/api/v1/obzor/postup"),
    ("GET", "/api/v1/obzor/rasxod"),
    ("GET", "/api/v1/obzor/excel"),
    ("GET", "/api/v1/obzor/items/{item_id}"),
    ("GET", "/api/v1/admin/etl/runs"),
    ("GET", "/api/v1/admin/etl/runs/{run_id}"),
    ("POST", "/api/v1/admin/etl/run"),
    ("GET", "/api/v1/admin/builds"),
    ("POST", "/api/v1/admin/builds/rollback"),
    ("GET", "/api/v1/admin/alert-rules"),
    ("GET", "/api/v1/admin/alert-rules/{code}/history"),
    ("PATCH", "/api/v1/admin/alert-rules/{code}"),
    ("GET", "/api/v1/admin/fin-assumptions"),
    ("PUT", "/api/v1/admin/fin-assumptions"),
    ("GET", "/api/v1/admin/settings"),
    ("PUT", "/api/v1/admin/settings/{key}"),
    ("GET", "/api/v1/admin/settings/{key}/history"),
    ("GET", "/api/v1/admin/integrations"),
    ("PUT", "/api/v1/admin/integrations/{name}"),
    ("POST", "/api/v1/admin/integrations/{name}/check"),
    ("GET", "/api/v1/admin/integrations/checks/{check_id}"),
    ("PATCH", "/api/v1/admin/positions/{position_id}"),
    ("PATCH", "/api/v1/admin/roles/{role_id}"),
    ("PATCH", "/api/v1/admin/users/{user_id}"),
    ("POST", "/api/v1/admin/positions"),
    ("POST", "/api/v1/admin/roles"),
    ("POST", "/api/v1/admin/users"),
    ("POST", "/api/v1/admin/users/{user_id}/block"),
    ("POST", "/api/v1/admin/users/{user_id}/reset-2fa"),
    ("POST", "/api/v1/admin/users/{user_id}/reset-password"),
    ("POST", "/api/v1/admin/users/{user_id}/unblock"),
    ("POST", "/api/v1/auth/2fa/enroll/begin"),
    ("POST", "/api/v1/auth/2fa/enroll/confirm"),
    ("POST", "/api/v1/auth/2fa/enroll/finish"),
    ("POST", "/api/v1/auth/2fa/enroll/start"),
    ("POST", "/api/v1/auth/2fa/offer/dismiss"),
    ("POST", "/api/v1/auth/2fa/verify"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password/change"),
})


def _resolve(route: BaseRoute) -> Iterator[object]:
    """`_IncludedRouter`larni rekursiv yoyib, chin (to'liq prefiksli, dependency'lari
    birlashtirilgan) marshrut kontekstlarini beradi.

    R2-1: har bir YAKUNIY (`_IncludedRouter` bo'lmagan) yozuv qat'iy tekshiriladi — u
    `APIRoute`ning o'zi (yoki uning kelib chiqishi `APIRoute`) bo'lishi, bo'sh bo'lmagan
    `methods`ga va `None` bo'lmagan `dependant`ga ega bo'lishi SHART, aks holda
    `NON_STANDARD_ROUTE_ALLOWLIST`da aniq ko'rsatilmagan bo'lsa `AssertionError`."""
    if isinstance(route, fastapi_routing._IncludedRouter):
        for candidate in route.effective_candidates():
            yield from _resolve(candidate)
        return
    original = getattr(route, "original_route", route)
    path = getattr(route, "path", getattr(original, "path", repr(original)))
    if not isinstance(original, APIRoute):
        assert path in NON_STANDARD_ROUTE_ALLOWLIST, (
            f"kutilmagan turdagi route (APIRoute emas): {original!r}"
        )
        return
    methods = getattr(route, "methods", None) or set()
    assert methods, f"{path}: bo'sh methods to'plami (route noto'g'ri aniqlandimi?)"
    dependant = getattr(route, "dependant", None)
    assert dependant is not None, f"{path}: dependant yo'q"
    yield route


def _calls(dep: Dependant) -> Iterator[object]:
    for sub in dep.dependencies:
        yield sub.call
        yield from _calls(sub)


def _routes(app: FastAPI | None = None) -> Iterator[tuple[str, str, Dependant]]:
    """(HTTP metod, to'liq yo'l, shu marshrutning to'liq — prefiks-darajasidagi
    dependency'lar bilan birlashtirilgan — `Dependant`i). `app` — `_resolve`ning qat'iy
    tekshiruvlarini "sinovchi" ilova ustida sinash uchun (standart: chin `create_app()`)."""
    for top in (app or create_app()).routes:
        for ctx in _resolve(top):
            for method in ctx.methods:
                yield method, ctx.path, ctx.dependant


def _matches_prefix(path: str, prefix: str) -> bool:
    """I5: `"/api/v1/admin"` prefiksi `"/api/v1/adminfoo"`ga emas, faqat aynan o'ziga yoki
    `"/api/v1/admin/..."`ga mos kelishi kerak."""
    return path == prefix or path.startswith(prefix + "/")


def _probe_endpoint() -> None:  # pragma: no cover -- hech qachon chaqirilmaydi
    return None


def test_resolve_raises_on_raw_route_inside_included_router() -> None:
    """R2-1: `_resolve`/`_routes`ning qat'iy tekshiruvi "sinovchi" ilova bilan — includelangan
    router ichiga qo'lda qo'shilgan xom Starlette `Route` (na `APIRoute`, na `dependant`ga
    ega) bilan — chindan ham yiqilishini tasdiqlaydi."""
    probe_router = APIRouter()
    probe_router.routes.append(StarletteRoute("/raw", _probe_endpoint, methods=["GET"]))
    probe_app = FastAPI()
    probe_app.include_router(probe_router)

    with pytest.raises(AssertionError):
        list(_routes(probe_app))


def test_route_table_matches_expected_set() -> None:
    """R2-1: yangi/yo'qolgan marshrut shu aniq to'plamni ONGLI ravishda yangilashni talab
    qiladi — deny-by-default qamrovi "sekin-asta shovqinsiz" torayib ketmasligi uchun."""
    actual = {(method, path) for method, path, _ in _routes()}
    assert actual == EXPECTED_ROUTES


def test_public_routes_correspond_to_existing_routes() -> None:
    existing = {(method, path) for method, path, _ in _routes()}
    for entry in PUBLIC:
        assert entry in existing, f"PUBLIC yozuvi {entry} hech qanday route'ga mos kelmaydi"


def test_every_non_public_route_requires_session() -> None:
    for method, path, dependant in _routes():
        if (method, path) in PUBLIC:
            continue
        assert get_ctx in set(_calls(dependant)), f"{method} {path} himoyasiz"


def _guard_satisfies(dependant: Dependant, needed: str) -> bool:
    """Prefiks ruxsati: all-of — kamida bittasi `needed` bilan boshlansa yetarli; any-of —
    HAR BIR ruxsat mos bo'lishi shart (aks holda any-of boshqa prefiksli ruxsat bilan
    admin route'ni ochib qo'yardi)."""
    for call in _calls(dependant):
        perms = set(getattr(call, "required_perms", ()))
        if not perms:
            continue
        check = all if getattr(call, "any_of", False) else any
        if check(p.startswith(needed) for p in perms):
            return True
    return False


def test_prefix_guard_rejects_any_of_with_foreign_permission() -> None:
    probe = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    mixed = Depends(require_perm("admin:users", "export:csv", any_of=True))
    strict = Depends(require_perm("admin:users", "admin:roles", any_of=True))
    probe.get("/mixed", dependencies=[mixed])(_probe_endpoint)
    probe.get("/strict", dependencies=[strict])(_probe_endpoint)
    by_path = {path: dep for _, path, dep in _routes(probe)}
    assert not _guard_satisfies(by_path["/mixed"], "admin:")
    assert _guard_satisfies(by_path["/strict"], "admin:")


def test_admin_and_audit_routes_require_matching_permission() -> None:
    for method, path, dependant in _routes():
        for prefix, needed in PREFIX_PERMS.items():
            if _matches_prefix(path, prefix):
                assert _guard_satisfies(dependant, needed), f"{method} {path}"


def test_positions_read_is_any_of_users_or_roles_while_writes_need_roles() -> None:
    for method, path, dependant in _routes():
        if not path.startswith("/api/v1/admin/positions"):
            continue
        perms: set[str] = set()
        for call in _calls(dependant):
            perms |= set(getattr(call, "required_perms", ()))
        expected = {"admin:users", "admin:roles"} if method == "GET" else {"admin:roles"}
        assert perms == expected, f"{method} {path}: {perms}"


def test_all_protected_routes_return_401_without_session() -> None:
    with TestClient(create_app(), base_url="https://testserver") as client:
        for method, path, _dependant in _routes():
            if (method, path) in PUBLIC:
                continue
            req_path = (
                path.replace("{user_id}", "1").replace("{role_id}", "1")
                .replace("{position_id}", "1")
                .replace("{session_id}", "00000000-0000-0000-0000-000000000000")
                .replace("{purpose}", "mfa").replace("{run_id}", "1")
                .replace("{code}", "turnover").replace("{key}", "builds.keep")
                .replace("{name}", "smtp").replace("{check_id}", "1")
                .replace("{item_id}", "1")
            )
            response = client.request(method, req_path, json={})
            assert response.status_code == 401, f"{method} {req_path}: {response.status_code}"


def _subs(dep: Dependant) -> Iterator[Dependant]:
    for sub in dep.dependencies:
        yield sub
        yield from _subs(sub)


def test_every_db_dependency_is_function_scoped() -> None:
    """Hotfix C2: `scope="request"`dagi `get_db` commit'ni javob yuborilgandan KEYINGA suradi;
    aralash scope esa bitta so'rovda IKKI sessiya beradi (kesh kaliti scope'ni o'z ichiga
    oladi) — `get_ctx`ning RLS `SET LOCAL`i endpoint sessiyasiga yetmay qolardi."""
    scopes = {
        (method, path, sub.scope)
        for method, path, dependant in _routes()
        for sub in _subs(dependant)
        if sub.call is get_db
    }
    assert scopes and {s for _, _, s in scopes} == {"function"}, sorted(
        x for x in scopes if x[2] != "function"
    )[:5]
