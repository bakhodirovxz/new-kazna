"""Manba nomi → konnektor. 1C, DirectBank va boshqalar keyingi rejalarda qo'shiladi."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.core.config import ConfigError, Settings, get_settings
from app.core.db import get_engine
from app.etl.file_connector import FileConnector
from app.etl.synthetic import SyntheticConnector
from app.etl.types import SourceConnector
from app.etl.zakupki.connector import ProcurementConnector
from app.etl.zakupki.portal import XaridPortal

KNOWN_SOURCES = ("synthetic", "file", "xarid")


def _xarid(settings: Settings) -> ProcurementConnector:
    portal = XaridPortal()  # hozircha PortalNotConfigured (spec 12, 1-savol)
    with get_engine("etl").connect() as conn:
        branches = {str(inn): str(code) for code, inn in conn.execute(text(
            "SELECT code, inn FROM dwh.dim_branch WHERE inn IS NOT NULL")).all()}
    return ProcurementConnector(portal, branches)


def make_connector(source: str, settings: Settings | None = None) -> SourceConnector:
    settings = settings or get_settings()
    if source == "synthetic":
        if settings.env == "prod":
            raise ConfigError("SyntheticConnector prod muhitida taqiqlangan")
        return SyntheticConnector(seed=settings.synthetic_seed)
    if source == "file":
        return FileConnector(Path(settings.etl_file_dir))
    if source == "xarid":
        return _xarid(settings)
    raise ValueError(f"noma'lum manba: {source}")
