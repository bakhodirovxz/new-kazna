from typing import Any

import pytest

from app.audit.service import AuditAction
from app.core import integrations, sysconfig
from app.core.config import get_settings
from app.dwh.reference import DEFAULT_SETTINGS, validate_setting
from app.etl.banks.registry import ADAPTER_NAMES, BANKS, BankAccount
from app.etl.notify import Notification

ACC = {"code": "BA-0123456789abcdef", "bank_code": "sqb", "branch_code": "UGE-02",
       "currency": "UZS", "gl_account": "5110", "last4": "0001"}
TOKEN = "123456789:" + "A" * 35


def test_s2_settings_defaults() -> None:
    assert set(BANKS) == {"sqb", "nbu", "asaka", "ipoteka", "xalq"}
    assert ADAPTER_NAMES == ("canonical",)
    assert DEFAULT_SETTINGS["banks.accounts"] == []
    assert DEFAULT_SETTINGS["banks.statement_branches"] == []
    assert DEFAULT_SETTINGS["banks.formats"] == dict.fromkeys(BANKS, "canonical")
    assert DEFAULT_SETTINGS["fx.currencies"][:3] == ["USD", "EUR", "CNY"]
    assert DEFAULT_SETTINGS["fx.lookback_days"] == 7
    assert DEFAULT_SETTINGS["cbu.enabled"] is False
    assert DEFAULT_SETTINGS["telegram.chat_ids"] == []
    for key, cron in (("etl.banks_cron", "30 9,12,15,18 * * *"), ("etl.cbu_cron", "0 8 * * *"),
                      ("telegram.summary_cron", "30 8 * * *")):
        assert DEFAULT_SETTINGS[key] == cron
        assert validate_setting(key, cron) == cron


def test_s2_settings_validation() -> None:
    assert validate_setting("banks.accounts", [ACC]) == [ACC]
    assert validate_setting("banks.statement_branches", ["UGE-02"]) == ["UGE-02"]
    assert validate_setting("banks.formats", {"sqb": "canonical"}) == {"sqb": "canonical"}
    assert validate_setting("telegram.chat_ids", ["-1001234567890", "42"]) == [
        "-1001234567890", "42"]
    bad: list[tuple[str, Any]] = [
        ("banks.accounts", [ACC, ACC]),
        ("banks.accounts", [{**ACC, "code": "20210000900100000001"}]),  # ochiq raqam emas, kod
        ("banks.accounts", [{**ACC, "bank_code": "citi"}]),
        ("banks.accounts", [{**ACC, "extra": 1}]),
        ("banks.statement_branches", ["UGE-02", "UGE-02"]),
        ("banks.formats", {"citi": "canonical"}),
        ("banks.formats", {"sqb": "mt940"}),
        ("fx.currencies", ["usd"]),
        ("fx.currencies", ["UZS"]),
        ("fx.currencies", []),
        ("fx.lookback_days", 0),
        ("etl.cbu_cron", "daily"),
        ("telegram.chat_ids", ["@channel"]),
        ("telegram.chat_ids", ["1"] * 11),
        ("cbu.enabled", "yes"),
    ]
    for key, value in bad:
        with pytest.raises(ValueError):
            validate_setting(key, value)


def test_integration_fields_are_admin_integrations_guarded() -> None:
    for key in ("cbu.enabled", "telegram.chat_ids"):
        d = sysconfig.REGISTRY[key]
        assert d.category == "integrations" and d.guarded and d.step_up, key
    assert set(integrations.INTEGRATIONS) >= {"telegram", "cbu"}
    _integ, sd = integrations.SECRETS["telegram.bot_token"]
    assert sd.validate(TOKEN) == TOKEN
    with pytest.raises(ValueError):
        sd.validate("nope")


def test_bank_account_model() -> None:
    account = BankAccount.model_validate(ACC)
    assert (account.code, account.last4) == ("BA-0123456789abcdef", "0001")


def test_egress_proxy_problem() -> None:
    proxy = get_settings().model_copy(update={"egress_proxy": "socks5://10.0.0.1:1080"})
    assert any("EGRESS_PROXY" in p for p in proxy.problems())
    ok = get_settings().model_copy(update={"egress_proxy": "http://10.0.0.1:3128"})
    assert not any("EGRESS_PROXY" in p for p in ok.problems())


def test_new_notification_kind_and_audit_action() -> None:
    assert Notification("bank_rows_rejected", "s", "b").kind == "bank_rows_rejected"
    assert AuditAction.TELEGRAM_SUMMARY_SENT.value == "notify.telegram.summary"
