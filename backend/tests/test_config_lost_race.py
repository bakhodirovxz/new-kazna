"""R2: FOR UPDATE kutib turgan so'rov poygada yutqazsa (joriy qator allaqachon almashgan) —
404/500 emas, 409 `conflict_modified`; noma'lum kod/kalit esa 404 bo'lib qoladi."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin import config_service as svc
from app.admin.dwh_schemas import AlertRuleUpdate, FinAssumptionItem, FinAssumptionsUpdate
from app.auth.context import AuthContext
from app.auth.permissions import PERMISSIONS
from app.core.db import get_engine, new_session
from app.core.errors import AppError, NotFoundError
from app.core.request_meta import ClientMeta
from tests.helpers import SeedUser

META = ClientMeta(ip=None, ua=None, request_id=None)


def _ctx(user: SeedUser) -> AuthContext:
    return AuthContext(user_id=user.id, username=user.username, full_name="A", role_code="admin",
                       permissions=frozenset(PERMISSIONS), branch_ids=None,
                       session_id=uuid.uuid4())


def _fin(value: float) -> FinAssumptionsUpdate:
    return FinAssumptionsUpdate(
        items=[FinAssumptionItem(scenario="tariff", year=2027, key="tariff_growth", value=value)])


def _race(lock_sql: str, params: dict[str, Any], winner: Callable[[Session], Any],
          loser: Callable[[Session], Any]) -> BaseException | None:
    """A qatorni qulflaydi, B (loser) kutadi, A (winner) commit qiladi, B uyg'onadi."""
    a = new_session()
    out: list[BaseException] = []

    def run() -> None:
        b = new_session()
        try:
            loser(b)
        except BaseException as exc:
            out.append(exc)
        finally:
            b.close()

    try:
        a.execute(text(lock_sql), params)
        t = threading.Thread(target=run)
        t.start()
        with get_engine("app").connect() as probe:
            for _ in range(100):  # B haqiqatan qulfda turganini kutamiz
                if probe.execute(text("SELECT count(*) FROM pg_stat_activity "
                                      "WHERE wait_event_type = 'Lock'")).scalar_one():
                    break
                time.sleep(0.1)
            else:
                pytest.fail("B qulfda kutmadi")
        winner(a)
        t.join(timeout=10)
    finally:
        a.close()
    return out[0] if out else None


def _assert_conflict(err: BaseException | None) -> None:
    assert isinstance(err, AppError) and err.status_code == 409
    assert err.code == "conflict_modified"


def test_alert_rule_lost_race_is_409(make_user: Callable[..., SeedUser]) -> None:
    ctx = _ctx(make_user("admin"))
    orig = next(r for r in svc.list_alert_rules(new_session()) if r.code == "turnover")
    lock = "SELECT 1 FROM core.alert_rules WHERE code = 'turnover' AND is_current FOR UPDATE"
    try:
        err = _race(
            lock, {},
            lambda a: svc.update_alert_rule(a, ctx, "turnover", AlertRuleUpdate(value=0.77), META),
            lambda b: svc.update_alert_rule(b, ctx, "turnover", AlertRuleUpdate(value=0.78), META))
        _assert_conflict(err)
    finally:
        svc.update_alert_rule(new_session(), ctx, "turnover",
                              AlertRuleUpdate(value=orig.threshold["value"]), META)


def test_fin_assumption_lost_race_is_409(make_user: Callable[..., SeedUser]) -> None:
    ctx = _ctx(make_user("admin"))
    orig = next(r for r in svc.list_fin_assumptions(new_session(), "tariff")
                if r.year == 2027 and r.key == "tariff_growth").value
    lock = ("SELECT 1 FROM core.fin_assumptions WHERE scenario = 'tariff' AND year = 2027 "
            "AND key = 'tariff_growth' AND is_current FOR UPDATE")
    try:
        err = _race(lock, {}, lambda a: svc.update_fin_assumptions(a, ctx, _fin(0.31), META),
                    lambda b: svc.update_fin_assumptions(b, ctx, _fin(0.32), META))
        _assert_conflict(err)
    finally:
        svc.update_fin_assumptions(new_session(), ctx, _fin(orig), META)


def test_setting_version_clash_is_409(make_user: Callable[..., SeedUser]) -> None:
    ctx = _ctx(make_user("admin"))
    key = "freshness.max_age_hours"
    svc.update_setting(new_session(), ctx, key, 7, META)  # joriy qator bo'lsin
    lock = "SELECT 1 FROM core.settings WHERE key = :k AND is_current FOR UPDATE"
    try:
        err = _race(lock, {"k": key}, lambda a: svc.update_setting(a, ctx, key, 8, META),
                    lambda b: svc.update_setting(b, ctx, key, 9, META))
        _assert_conflict(err)
    finally:
        svc.update_setting(new_session(), ctx, key, 6, META)


def test_unknown_alert_rule_stays_404(make_user: Callable[..., SeedUser]) -> None:
    ctx = _ctx(make_user("admin"))
    with pytest.raises(NotFoundError):
        svc.update_alert_rule(new_session(), ctx, "nope", AlertRuleUpdate(value=1), META)
