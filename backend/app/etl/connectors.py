"""Manba nomi → konnektor."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from app.core import integrations, sysconfig
from app.core.config import ConfigError, Settings, get_settings
from app.core.db import get_engine
from app.dwh.reference import current_setting
from app.etl.askue.connector import AskueConnector
from app.etl.askue.export import DirectoryExport
from app.etl.askue.registry import AskueStation
from app.etl.banks.connector import BankFileConnector
from app.etl.banks.directbank import DIRECTBANK_MESSAGE
from app.etl.banks.registry import BankAccount
from app.etl.cbu.client import CbuClient
from app.etl.cbu.connector import CbuRatesConnector
from app.etl.file_connector import FileConnector
from app.etl.hr.client import HrApiClient, ca_context
from app.etl.hr.connector import HrConnector
from app.etl.hr.registry import HrOrg
from app.etl.hr.source import HrApiSource, MehnatSource
from app.etl.manual_connector import ManualConnector
from app.etl.onec.client import OneCClient, OneCConfig
from app.etl.onec.connector import OneCConnector, OrgMap
from app.etl.onec.sklad import OneCSkladConnector, sklad_config
from app.etl.rebuild import RebuildConnector
from app.etl.synthetic import SyntheticConnector
from app.etl.types import SourceConnector
from app.etl.zakupki.connector import ProcurementConnector
from app.etl.zakupki.portal import XaridPortal

KNOWN_SOURCES = ("synthetic", "file", "onec", "banks", "cbu", "directbank", "xarid", "hr",
                 "mehnat", "askue", "onec_sklad", "manual", "rebuild")


def _xarid(settings: Settings) -> ProcurementConnector:
    portal = XaridPortal()  # hozircha PortalNotConfigured (spec 12, 1-savol)
    with get_engine("etl").connect() as conn:
        branches = {str(inn): str(code) for code, inn in conn.execute(text(
            "SELECT code, inn FROM dwh.dim_branch WHERE inn IS NOT NULL")).all()}
    return ProcurementConnector(portal, branches)


def _onec() -> OneCConnector:
    """Konfiguratsiya (manzil, login/parol) har ishga tushirishda panelda o'qiladi (U6)."""
    with get_engine("etl").connect() as conn:
        config = OneCConfig.load(conn)  # sozlanmagan bo'lsa ConfigError
        orgs = current_setting(conn, "onec.orgs")
        income = bool(current_setting(conn, "onec.income_enabled"))
        limit = int(current_setting(conn, "onec.page_limit"))
    if not orgs:
        raise ConfigError("onec.orgs bo'sh: `python -m app.cli onec-orgs --file …` yoki "
                          "«Настройки → 1С» bilan sozlang")
    return OneCConnector(OneCClient(config), [OrgMap(**org) for org in orgs],
                         income_enabled=income, page_limit=limit)


def _banks(settings: Settings) -> BankFileConnector:
    with get_engine("etl").connect() as conn:
        accounts = sysconfig.current(conn, "banks.accounts")
        formats = sysconfig.current(conn, "banks.formats")
    if not accounts:
        raise ConfigError("banks.accounts bo'sh: `python -m app.cli bank-accounts --file …` "
                          "bilan sozlang")
    return BankFileConnector(Path(settings.bank_inbox_dir), Path(settings.bank_archive_dir),
                             [BankAccount.model_validate(a) for a in accounts],
                             formats=dict(formats))


def cbu_connector(settings: Settings, *, date_from: date | None = None,
                  date_to: date | None = None) -> CbuRatesConnector:
    with get_engine("etl").connect() as conn:
        if not sysconfig.current(conn, "cbu.enabled"):
            raise ConfigError("cbu.enabled=false — ЦБ kurslari yuklanmaydi (Администрирование → "
                              "Интеграции)")
        currencies = list(sysconfig.current(conn, "fx.currencies"))
        days = int(sysconfig.current(conn, "fx.lookback_days"))
    client = CbuClient(settings.cbu_base_url, proxy=settings.egress_proxy)
    return CbuRatesConnector(client, currencies, days=days, date_from=date_from, date_to=date_to)


def _hr(settings: Settings) -> HrConnector:
    """HR API: manzil va login/parol — admin panel (core.settings + shifrlangan sirlar, U6)."""
    with get_engine("etl").connect() as conn:
        base_url = str(sysconfig.current(conn, "hr.base_url"))
        if not base_url:
            raise ConfigError("hr.base_url berilmagan — HR API konnektori o'chiq "
                              "(Администрирование → Интеграции)")
        username = integrations.secret(conn, "hr.username")
        password = integrations.secret(conn, "hr.password")
        if not username or not password:
            raise ConfigError("hr.username/hr.password sirlari bo'sh "
                              "(Администрирование → Интеграции)")
        orgs = sysconfig.current(conn, "hr.orgs")
        path = str(sysconfig.current(conn, "hr.breakdown_path"))
    client = HrApiClient(base_url, username, password, verify=ca_context(settings.hr_ca_file),
                         proxy=settings.egress_proxy)
    return HrConnector(HrApiSource(client, path), [HrOrg.model_validate(o) for o in orgs])


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


def _onec_sklad() -> OneCSkladConnector:
    # U6: manzil va hisob ma'lumotlari faqat panel/integrations'dan, ishlatish paytida o'qiladi.
    with get_engine("etl").connect() as conn:
        config = sklad_config(conn)  # sozlanmagan bo'lsa ConfigError
        orgs = sysconfig.current(conn, "onec.orgs")
        months = int(sysconfig.current(conn, "onec.sklad_months"))
    if not orgs:
        raise ConfigError("onec.orgs bo'sh: Администрирование → Настройки → «Организации 1С»")
    return OneCSkladConnector(OneCClient(config), [OrgMap(**org) for org in orgs], months=months)




def make_connector(source: str, settings: Settings | None = None) -> SourceConnector:
    settings = settings or get_settings()
    if source == "synthetic":
        if settings.env == "prod":
            raise ConfigError("SyntheticConnector prod muhitida taqiqlangan")
        return SyntheticConnector(seed=settings.synthetic_seed)
    if source == "rebuild":
        return RebuildConnector()  # S5: ekstraktsiyasiz qayta hisob (dev va prod'da)
    if source == "onec_sklad":
        return _onec_sklad()
    if source == "askue":
        return _askue(settings)
    if source == "file":
        return FileConnector(Path(settings.etl_file_dir))
    if source == "onec":
        return _onec()
    if source == "cbu":
        return cbu_connector(settings)
    if source == "banks":
        return _banks(settings)
    if source == "directbank":
        raise ConfigError(DIRECTBANK_MESSAGE)
    if source == "xarid":
        return _xarid(settings)
    if source == "hr":
        return _hr(settings)
    if source == "mehnat":
        MehnatSource()  # TZ 8: 3-bosqich — har doim MehnatNotConfigured (ConfigError)
        raise ConfigError("mehnat.uz")  # pragma: no cover — erishib bo'lmaydi
    if source == "manual":
        return ManualConnector()
    raise ValueError(f"noma'lum manba: {source}")
