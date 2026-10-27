"""Manba nomi → konnektor."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.core import sysconfig
from app.core.config import ConfigError, Settings, get_settings
from app.core.db import get_engine
from app.dwh.reference import current_setting
from app.etl.banks.connector import BankFileConnector
from app.etl.banks.directbank import DIRECTBANK_MESSAGE
from app.etl.banks.registry import BankAccount
from app.etl.cbu.client import CbuClient
from app.etl.cbu.connector import CbuRatesConnector
from app.etl.file_connector import FileConnector
from app.etl.onec.client import OneCClient, OneCConfig
from app.etl.onec.connector import OneCConnector, OrgMap
from app.etl.synthetic import SyntheticConnector
from app.etl.types import SourceConnector


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


KNOWN_SOURCES = ("synthetic", "file", "onec", "banks", "cbu", "directbank")


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


def make_connector(source: str, settings: Settings | None = None) -> SourceConnector:
    settings = settings or get_settings()
    if source == "synthetic":
        if settings.env == "prod":
            raise ConfigError("SyntheticConnector prod muhitida taqiqlangan")
        return SyntheticConnector(seed=settings.synthetic_seed)
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
    raise ValueError(f"noma'lum manba: {source}")
