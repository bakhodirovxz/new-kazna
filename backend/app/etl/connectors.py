"""Manba nomi → konnektor. DirectBank va boshqalar keyingi rejalarda qo'shiladi."""

from __future__ import annotations

from pathlib import Path

from app.core.config import ConfigError, Settings, get_settings
from app.core.db import get_engine
from app.dwh.reference import current_setting
from app.etl.file_connector import FileConnector
from app.etl.onec.client import OneCClient, OneCConfig
from app.etl.onec.connector import OneCConnector, OrgMap
from app.etl.synthetic import SyntheticConnector
from app.etl.types import SourceConnector

KNOWN_SOURCES = ("synthetic", "file", "onec")


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
    raise ValueError(f"noma'lum manba: {source}")
