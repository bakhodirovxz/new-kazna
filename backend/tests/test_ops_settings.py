from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import ops
from app.core import sysconfig
from app.core.db import get_engine

Put = Callable[[str, object], None]


@pytest.fixture
def restore_row() -> Iterator[None]:
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.settings WHERE key = :k"), {"k": ops.RESTORE_KEY})


def test_ops_keys_are_tighten_only() -> None:
    expected = {"ops.restore_max_age_days": (40, "hi"), "ops.dek_max_age_days": (365, "hi"),
                "ops.clock_skew_max_seconds": (60, "hi"), "ops.tls_warn_days": (30, "lo"),
                "ops.tls_critical_days": (7, "lo")}
    for key, (bound, side) in expected.items():
        d = sysconfig.REGISTRY[key]
        assert d.default == bound == getattr(d, side) and d.step_up and d.category == "ops", key
    # ops.py konstantalari = reyestr standartlari (ikkinchi nusxa uzilib ketmasin)
    assert ops.RESTORE_MAX_AGE.days == expected["ops.restore_max_age_days"][0]
    assert ops.DEK_MAX_AGE.days == expected["ops.dek_max_age_days"][0]
    assert ops.CLOCK_SKEW_MAX.total_seconds() == expected["ops.clock_skew_max_seconds"][0]
    assert ops.TLS_WARN.days == expected["ops.tls_warn_days"][0]
    assert ops.TLS_CRITICAL.days == expected["ops.tls_critical_days"][0]


def test_check_restore_accepts_threshold() -> None:
    now = datetime.now(UTC)
    value = {"at": (now - timedelta(days=20)).isoformat(), "result": "ok", "rto_ok": True}
    assert ops.check_restore(value, now) == []
    assert [p.code for p in ops.check_restore(value, now, max_age=timedelta(days=10))] == [
        "restore_test_overdue"]


@pytest.mark.usefixtures("restore_row")
def test_ops_check_uses_panel_thresholds(setting: Put) -> None:
    now = datetime.now(UTC)
    with get_engine("app").begin() as conn:
        ops.record_restore_test(conn, ops.RestoreResult(
            at=now - timedelta(days=20), result="ok", duration_seconds=60, backup="t", details=""))
    assert "restore_test_overdue" not in {p.code for p in ops.ops_check(now=now)}
    setting("ops.restore_max_age_days", 10)
    setting("ops.clock_skew_max_seconds", 5)
    codes = {p.code for p in ops.ops_check(
        now=now, app_clock=lambda: datetime.now(UTC) + timedelta(seconds=20))}
    assert {"restore_test_overdue", "clock_skew"} <= codes
