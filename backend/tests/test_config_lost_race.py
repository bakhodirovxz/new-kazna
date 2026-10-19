"""R2: FOR UPDATE kutib turgan so'rov poygada yutqazsa (joriy qator allaqachon almashgan) —
404/500 emas, 409 `conflict_modified`; noma'lum kod/kalit esa 404 bo'lib qoladi."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin import config_service as svc
from app.admin.dwh_schemas import AlertRuleUpdate, FinAssumptionItem, FinAssumptionsUpdate
from app.auth.context import AuthContext
from app.auth.permissions import PERMISSIONS
from app.core.db import get_engine, new_session
from app.core.errors import AppError, NotFoundError
from app.core.request_meta import ClientMeta
from app.main import create_app
from tests.helpers import SeedUser, login

META = ClientMeta(ip=None, ua=None, request_id=None)


def _ctx(user: SeedUser) -> AuthContext:
    return AuthContext(user_id=user.id, username=user.username, full_name="A", role_code="admin",
                       permissions=frozenset(PERMISSIONS), branch_ids=None,
                       session_id=uuid.uuid4())


def _fin(value: float) -> FinAssumptionsUpdate:
    return FinAssumptionsUpdate(
        items=[FinAssumptionItem(scenario="tariff", year=2027, key="tariff_growth", value=value)])


def _race(lock_sql: str, params: dict[str, Any], winner: Callable[[Session], Any],
          loser: Callable[[Session], Any]) -> tuple[Any, BaseException | None]:
    """A qatorni qulflaydi, B (loser) kutadi, A (winner) commit qiladi, B uyg'onadi."""
    out: list[Any] = []
    errs: list[BaseException] = []

    def run() -> None:
        with new_session() as b:
            try:
                out.append(loser(b))
            except BaseException as exc:
                errs.append(exc)

    with new_session() as a:
        a.execute(text(lock_sql), params)
        pid = a.execute(text("SELECT pg_backend_pid()")).scalar_one()
        t = threading.Thread(target=run)
        t.start()
        with get_engine("app").connect() as probe:
            for _ in range(100):  # A'ni kutayotgan backend (B) paydo bo'lguncha
                if probe.execute(text("SELECT count(*) FROM pg_stat_activity "
                                      "WHERE :p = ANY(pg_blocking_pids(pid))"),
                                 {"p": pid}).scalar_one():
                    break
                time.sleep(0.1)
            else:
                pytest.fail("B qulfda kutmadi")
        winner(a)
        t.join(timeout=10)
    return (out[0] if out else None), (errs[0] if errs else None)


def _assert_conflict(err: BaseException | None) -> None:
    assert isinstance(err, AppError) and err.status_code == 409
    assert err.code == "conflict_modified"


def _rule(code: str) -> Any:
    with new_session() as s:
        return next(r for r in svc.list_alert_rules(s) if r.code == code)


def _restore_rule(ctx: AuthContext, code: str, value: float) -> None:
    with new_session() as s:
        svc.update_alert_rule(s, ctx, code, AlertRuleUpdate(value=value), META)


_RULE_LOCK = "SELECT 1 FROM core.alert_rules WHERE code = 'turnover' AND is_current FOR UPDATE"


def test_alert_rule_lost_race_is_409(make_user: Callable[..., SeedUser]) -> None:
    ctx = _ctx(make_user("admin"))
    orig = _rule("turnover").threshold["value"]
    try:
        _, err = _race(
            _RULE_LOCK, {},
            lambda a: svc.update_alert_rule(a, ctx, "turnover", AlertRuleUpdate(value=0.77), META),
            lambda b: svc.update_alert_rule(b, ctx, "turnover", AlertRuleUpdate(value=0.78), META))
        _assert_conflict(err)
    finally:
        _restore_rule(ctx, "turnover", orig)


def test_lost_race_http_body_is_409_conflict_modified(
    make_user: Callable[..., SeedUser],
) -> None:
    admin = make_user("admin")
    ctx = _ctx(admin)
    orig = _rule("turnover").threshold["value"]
    with TestClient(create_app(), base_url="https://testserver") as client:
        login(client, admin)
        try:
            resp, err = _race(
                _RULE_LOCK, {},
                lambda a: svc.update_alert_rule(a, ctx, "turnover", AlertRuleUpdate(value=0.77),
                                                META),
                lambda _b: client.patch("/api/v1/admin/alert-rules/turnover",
                                        json={"value": 0.78}))
            assert err is None
            assert resp.status_code == 409
            body = resp.json()["error"]
            assert body["code"] == "conflict_modified"
            assert body["message"] == "Запись изменена другим пользователем, обновите страницу"
        finally:
            _restore_rule(ctx, "turnover", orig)


def test_fin_assumption_lost_race_is_409(make_user: Callable[..., SeedUser]) -> None:
    ctx = _ctx(make_user("admin"))
    with new_session() as s:
        orig = next(r for r in svc.list_fin_assumptions(s, "tariff")
                    if r.year == 2027 and r.key == "tariff_growth").value
    lock = ("SELECT 1 FROM core.fin_assumptions WHERE scenario = 'tariff' AND year = 2027 "
            "AND key = 'tariff_growth' AND is_current FOR UPDATE")

    def put(value: float) -> Callable[[Session], Any]:
        return lambda db: svc.update_fin_assumptions(db, ctx, _fin(value), META)

    try:
        _, err = _race(lock, {}, put(0.31), put(0.32))
        _assert_conflict(err)
    finally:
        with new_session() as s:
            svc.update_fin_assumptions(s, ctx, _fin(orig), META)


def test_fin_items_are_locked_in_sorted_order(make_user: Callable[..., SeedUser]) -> None:
    ctx = _ctx(make_user("admin"))
    items = [FinAssumptionItem(scenario="tariff", year=y, key="tariff_growth", value=0.0)
             for y in (2028, 2027)]
    with new_session() as s:
        before = {r.year: r.value for r in svc.list_fin_assumptions(s, "tariff")
                  if r.key == "tariff_growth" and r.year in (2027, 2028)}
        out = svc.update_fin_assumptions(
            s, ctx, FinAssumptionsUpdate(items=[
                i.model_copy(update={"value": before[i.year] + 0.01}) for i in items]), META)
        assert out  # ikki element teskari tartibda berilsa ham xatosiz o'tadi
    with new_session() as s:
        svc.update_fin_assumptions(s, ctx, FinAssumptionsUpdate(items=[
            i.model_copy(update={"value": before[i.year]}) for i in items]), META)


def test_setting_version_clash_is_409(make_user: Callable[..., SeedUser]) -> None:
    ctx = _ctx(make_user("admin"))
    key = "freshness.max_age_hours"
    with new_session() as s:
        svc.update_setting(s, ctx, key, 7, META)  # joriy qator bo'lsin
    lock = "SELECT 1 FROM core.settings WHERE key = :k AND is_current FOR UPDATE"
    try:
        _, err = _race(lock, {"k": key}, lambda a: svc.update_setting(a, ctx, key, 8, META),
                       lambda b: svc.update_setting(b, ctx, key, 9, META))
        _assert_conflict(err)
    finally:
        with new_session() as s:
            svc.update_setting(s, ctx, key, 6, META)


def test_unknown_alert_rule_stays_404(make_user: Callable[..., SeedUser]) -> None:
    ctx = _ctx(make_user("admin"))
    with pytest.raises(NotFoundError), new_session() as s:
        svc.update_alert_rule(s, ctx, "nope", AlertRuleUpdate(value=1), META)
