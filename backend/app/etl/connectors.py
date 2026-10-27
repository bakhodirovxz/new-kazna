"""Manba nomi → konnektor. 1C, DirectBank va boshqalar keyingi rejalarda qo'shiladi."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.core import integrations, sysconfig
from app.core.config import ConfigError, Settings, get_settings
from app.core.db import get_engine
from app.etl.askue.connector import AskueConnector
from app.etl.askue.export import DirectoryExport
from app.etl.askue.registry import AskueStation
from app.etl.file_connector import FileConnector
from app.etl.onec.client import OneCClient, verify_setting
from app.etl.onec.connector import OrgMap
from app.etl.onec.sklad import OneCSkladConnector
from app.etl.synthetic import SyntheticConnector
from app.etl.types import SourceConnector

KNOWN_SOURCES = ("synthetic", "file", "askue", "onec_sklad")


def _askue(settings: Settings) -> AskueConnector:
    with get_engine("etl").connect() as conn:
        stations = sysconfig.current(conn, "askue.stations")
        days = int(sysconfig.current(conn, "askue.inbox_days"))
        caps = {r.code: r.capacity_mw for r in conn.execute(text(
            "SELECT code, capacity_mw FROM dwh.dim_branch WHERE capacity_mw IS NOT NULL"))}
    if not stations:
        raise ConfigError("askue.stations bo'sh: `python -m app.cli askue-stations --file …` "
                          "bilan sozlang")
    return AskueConnector(DirectoryExport(Path(settings.askue_inbox_dir), max_age_days=days),
                          [AskueStation.model_validate(s) for s in stations], capacities=caps)


def _onec_sklad(settings: Settings) -> OneCSkladConnector:
    # U6: manzil va hisob ma'lumotlari faqat panel/integrations'dan, ishlatish paytida o'qiladi.
    with get_engine("etl").connect() as conn:
        base_url = str(sysconfig.current(conn, "onec_sklad.base_url"))
        if not base_url:
            raise ConfigError("onec_sklad.base_url berilmagan — 1C ombor konnektori o'chiq")
        username = integrations.secret(conn, "onec_sklad.username")
        password = integrations.secret(conn, "onec_sklad.password")
        orgs = sysconfig.current(conn, "onec.orgs")
        months = int(sysconfig.current(conn, "onec.sklad_months"))
    if not username or not password:
        raise ConfigError("onec_sklad.username/onec_sklad.password sirlari panelda berilmagan")
    if not orgs:
        raise ConfigError("onec.orgs bo'sh: Администрирование → Настройки → «Организации 1С»")
    client = OneCClient(base_url, username, password, verify=verify_setting(settings.onec_ca_file),
                        allow_http=settings.onec_allow_http)
    return OneCSkladConnector(client, [OrgMap.model_validate(org) for org in orgs], months=months)


def make_connector(source: str, settings: Settings | None = None) -> SourceConnector:
    settings = settings or get_settings()
    if source == "synthetic":
        if settings.env == "prod":
            raise ConfigError("SyntheticConnector prod muhitida taqiqlangan")
        return SyntheticConnector(seed=settings.synthetic_seed)
    if source == "onec_sklad":
        return _onec_sklad(settings)
    if source == "askue":
        return _askue(settings)
    if source == "file":
        return FileConnector(Path(settings.etl_file_dir))
    raise ValueError(f"noma'lum manba: {source}")
