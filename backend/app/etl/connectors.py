"""Manba nomi → konnektor. 1C, DirectBank va boshqalar keyingi rejalarda qo'shiladi."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.core import integrations, sysconfig
from app.core.config import ConfigError, Settings, get_settings
from app.core.db import get_engine
from app.etl.file_connector import FileConnector
from app.etl.hr.client import HrApiClient, ca_context
from app.etl.hr.connector import HrConnector
from app.etl.hr.registry import HrOrg
from app.etl.hr.source import HrApiSource, MehnatSource
from app.etl.synthetic import SyntheticConnector
from app.etl.types import SourceConnector
from app.etl.zakupki.connector import ProcurementConnector
from app.etl.zakupki.portal import XaridPortal

KNOWN_SOURCES = ("synthetic", "file", "xarid", "hr", "mehnat")


def _xarid(settings: Settings) -> ProcurementConnector:
    portal = XaridPortal()  # hozircha PortalNotConfigured (spec 12, 1-savol)
    with get_engine("etl").connect() as conn:
        branches = {str(inn): str(code) for code, inn in conn.execute(text(
            "SELECT code, inn FROM dwh.dim_branch WHERE inn IS NOT NULL")).all()}
    return ProcurementConnector(portal, branches)


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
    if source == "hr":
        return _hr(settings)
    if source == "mehnat":
        MehnatSource()  # TZ 8: 3-bosqich — har doim MehnatNotConfigured (ConfigError)
        raise ConfigError("mehnat.uz")  # pragma: no cover — erishib bo'lmaydi
    raise ValueError(f"noma'lum manba: {source}")
