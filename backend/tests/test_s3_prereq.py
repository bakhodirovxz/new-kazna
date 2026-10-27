from typing import Any

import pytest

from app.core import integrations
from app.core.config import get_settings
from app.dwh.reference import DEFAULT_SETTINGS, validate_setting
from app.etl.askue.registry import STATION_KINDS, AskueStation, normalize_name
from app.etl.notify import Notification

ST = {"code": "CHARVAK-1", "name": "Chorvoq GES", "branch_code": "UGE-02"}


def test_s3_settings_defaults() -> None:
    assert DEFAULT_SETTINGS["askue.stations"] == []
    assert DEFAULT_SETTINGS["askue.inbox_days"] == 7
    assert DEFAULT_SETTINGS["askue.live_keep_days"] == 35
    assert DEFAULT_SETTINGS["askue.live_stale_minutes"] == 30
    assert DEFAULT_SETTINGS["onec.sklad_months"] == 13
    assert DEFAULT_SETTINGS["askue.live_url"] == ""
    assert DEFAULT_SETTINGS["onec_sklad.base_url"] == ""
    for key, cron in (("askue.live_cron", "*/10 * * * *"), ("etl.askue_cron", "15 7 * * *"),
                      ("etl.onec_sklad_full_cron", "30 3 * * *"),
                      ("etl.onec_sklad_incremental_cron", "30 10,13,16 * * *")):
        assert DEFAULT_SETTINGS[key] == cron
        assert validate_setting(key, cron) == cron
    assert STATION_KINDS == ("ges", "cascade")


def test_s3_settings_validation() -> None:
    other = {"code": "CHARVAK-2", "name": "Chorvoq GES-2", "branch_code": "UGE-02"}
    assert validate_setting("askue.stations", [ST, other]) == [ST, other]
    assert validate_setting("askue.live_url", "https://treplex.test/api/cascades/ges")
    assert validate_setting("onec_sklad.base_url", "https://1c.uge.uz/con2026/hs/sklad")
    bad: list[tuple[str, Any]] = [
        ("askue.stations", [ST, ST]),
        ("askue.stations", [ST, {**other, "name": "  chorvoq   ges "}]),  # nom takrori
        ("askue.stations", [{**ST, "code": "bad code"}]),
        ("askue.stations", [{**ST, "extra": 1}]),
        ("askue.stations", [{**ST, "branch_code": ""}]),
        ("askue.inbox_days", 0),
        ("askue.inbox_days", 61),
        ("askue.live_keep_days", 0),
        ("askue.live_stale_minutes", 1),
        ("onec.sklad_months", 0),
        ("onec.sklad_months", 37),
        ("etl.askue_cron", "daily"),
        ("askue.live_url", "http://treplex.test/api"),
        ("onec_sklad.base_url", "ftp://1c.uge.uz"),
    ]
    for key, value in bad:
        with pytest.raises(ValueError):
            validate_setting(key, value)


def test_station_model_and_normalization() -> None:
    station = AskueStation.model_validate(ST)
    assert (station.code, station.branch_code) == ("CHARVAK-1", "UGE-02")
    assert normalize_name("  To‘polang   GES ") == normalize_name("to'polang ges")
    assert normalize_name("Qodiriya GESlari") == "qodiriya geslari"


def test_s3_integrations_registered() -> None:
    live = integrations.INTEGRATIONS["askue_live"]
    assert live.fields == live.endpoint == ("askue.live_url",) and not live.secrets
    sklad = integrations.INTEGRATIONS["onec_sklad"]
    assert sklad.endpoint == ("onec_sklad.base_url",)
    assert {s.name for s in sklad.secrets} == {"onec_sklad.username", "onec_sklad.password"}
    assert all(s.env is None for s in sklad.secrets)  # yangi integratsiya: yagona manba panel
    assert "onec_sklad" in integrations.RULES


def test_s3_config_and_notification_kind() -> None:
    assert get_settings().askue_inbox_dir == "/data/import/askue"
    assert Notification("askue_rows_rejected", "s", "b").kind == "askue_rows_rejected"
