from collections.abc import Callable
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.auth.permissions import Perm
from app.core import sysconfig
from app.core.config import Settings
from app.core.db import get_engine
from app.dwh.reference import (
    DEFAULT_SETTINGS,
    current_setting,
    ensure_reference,
    validate_setting,
)
from tests.helpers import clear_setting, put_setting

Put = Callable[[str, object], None]

# docs/security da e'lon qilingan qiymat = eng zaif ruxsat etilgan chegara (spec 3.3).
WEAKEST: dict[str, tuple[str, int]] = {
    "security.session_idle_minutes": ("hi", 30),
    "security.session_absolute_hours": ("hi", 12),
    "security.password_max_age_days": ("hi", 90),
    "security.login_max_failures": ("hi", 5),
    "security.login_lockout_minutes": ("lo", 15),
    "security.password_min_length": ("lo", 12),
    "security.password_history": ("lo", 5),
    "ratelimit.login_per_min": ("hi", 10),
    "ratelimit.mfa_per_min": ("hi", 20),
    "ratelimit.api_per_min": ("hi", 300),
    "ratelimit.password_change_per_15min": ("hi", 5),
    "retention.audit_months": ("lo", 12),
    "retention.fact_years": ("lo", 5),
}


class _Broken:
    def connect(self) -> Any:
        raise OperationalError("SELECT 1", {}, Exception("db down"))


def test_registry_is_consistent() -> None:
    keys = [d.key for d in sysconfig._DEFS]
    assert len(keys) == len(set(keys)) == len(sysconfig.REGISTRY)
    for d in sysconfig.REGISTRY.values():
        assert sysconfig.KEY_RE.fullmatch(d.key) and len(d.key) <= 64, d.key
        assert d.title and d.category, d.key
        assert d.validate(d.default) == d.default, d.key
        if d.kind in ("int", "float"):
            assert d.lo is not None and d.hi is not None and d.lo <= d.default <= d.hi, d.key
        if d.perm != Perm.ADMIN_SETTINGS:
            assert d.guarded and d.step_up, d.key


def test_env_defaults_match_settings_defaults() -> None:
    for d in sysconfig.REGISTRY.values():
        if d.env is not None and d.env_attr is None:
            default = Settings.model_fields[d.env].default
            assert (default.get_secret_value() if isinstance(default, SecretStr) else default) \
                == d.default, d.key
    assert sysconfig.REGISTRY["notify.email_to"].default == []


def test_security_bounds_are_tighten_only() -> None:
    for key, (side, bound) in WEAKEST.items():
        d = sysconfig.REGISTRY[key]
        assert getattr(d, side) == bound == d.default, key
        assert d.guarded and d.env is None, key
    for key in WEAKEST:
        if key.startswith(("security.", "ratelimit.")) or key == "retention.audit_months":
            assert sysconfig.REGISTRY[key].perm == Perm.ADMIN_SECURITY, key


def test_resolve_prefers_panel_then_env_then_default(monkeypatch: pytest.MonkeyPatch) -> None:
    d = sysconfig.REGISTRY["smtp.host"]
    monkeypatch.setattr(sysconfig, "get_settings", lambda: Settings(smtp_host="relay.uge.uz"))
    assert sysconfig.resolve(d, {}) == ("relay.uge.uz", "env")
    assert sysconfig.resolve(d, {"smtp.host": "mail.uge.uz"}) == ("mail.uge.uz", "panel")
    monkeypatch.setattr(sysconfig, "get_settings", lambda: Settings(smtp_host=""))
    assert sysconfig.resolve(d, {})[0] == ""
    to = sysconfig.REGISTRY["notify.email_to"]
    monkeypatch.setattr(sysconfig, "get_settings",
                        lambda: Settings(smtp_to="a@uge.uz, b@uge.uz"))
    assert sysconfig.resolve(to, {}) == (["a@uge.uz", "b@uge.uz"], "env")


def test_invalid_panel_value_falls_back() -> None:
    d = sysconfig.REGISTRY["security.session_idle_minutes"]
    assert sysconfig.resolve(d, {d.key: 45}) == (30, "default")
    assert sysconfig.resolve(d, {d.key: "10"}) == (30, "default")  # strict: satr emas
    assert sysconfig.resolve(d, {d.key: True}) == (30, "default")
    assert sysconfig.resolve(d, {d.key: 10}) == (10, "panel")


def test_current_reads_inside_transaction(setting: Put) -> None:
    setting("builds.keep", 4)
    with get_engine("app").connect() as conn:
        assert sysconfig.current(conn, "builds.keep") == 4
        assert current_setting(conn, "builds.keep") == 4
        assert sysconfig.current(conn, "freshness.max_age_hours") == 6
        with pytest.raises(KeyError):
            sysconfig.current(conn, "no.such")


def test_value_is_cached_until_invalidate() -> None:
    assert sysconfig.value("partitions.months_ahead") == 3
    try:
        put_setting("partitions.months_ahead", 5, invalidate=False)
        assert sysconfig.value("partitions.months_ahead") == 3  # kesh (≤ 30 s)
        sysconfig.invalidate()
        assert sysconfig.value("partitions.months_ahead") == 5
    finally:
        clear_setting("partitions.months_ahead")
    with pytest.raises(KeyError):
        sysconfig.value("no.such")


def test_value_keeps_last_snapshot_when_db_fails(
    setting: Put, monkeypatch: pytest.MonkeyPatch
) -> None:
    setting("builds.keep", 4)
    assert sysconfig.value("builds.keep") == 4
    monkeypatch.setattr(sysconfig, "get_engine", lambda role="app": _Broken())
    monkeypatch.setattr(sysconfig, "CACHE_TTL", 0.0)
    assert sysconfig.value("builds.keep") == 4


def test_value_defaults_when_db_down_without_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    sysconfig.invalidate()
    monkeypatch.setattr(sysconfig, "get_engine", lambda role="app": _Broken())
    assert sysconfig.value("security.session_idle_minutes") == 30


def test_reference_aliases_follow_registry() -> None:
    assert {k: d.default for k, d in sysconfig.REGISTRY.items()} == DEFAULT_SETTINGS
    assert validate_setting("builds.keep", 4) == 4
    with pytest.raises(ValueError):
        validate_setting("builds.keep", 11)
    with pytest.raises(KeyError):
        validate_setting("no.such", 1)


def test_ensure_reference_does_not_seed_settings() -> None:
    with get_engine("app").begin() as conn:
        ensure_reference(conn)
    with get_engine("app").connect() as conn:
        seeded = conn.execute(text(
            "SELECT count(*) FROM core.settings WHERE key LIKE 'security.%' "
            "OR key LIKE 'smtp.%'")).scalar_one()
    assert seeded == 0
