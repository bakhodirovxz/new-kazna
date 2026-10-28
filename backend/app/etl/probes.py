"""Integratsiya ulanish tekshiruvlari navbati (worker, egress bor joyda).

Natija — faqat xavfsiz kod; istisno matni saqlanmaydi (unda sir bo'lishi mumkin).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
from sqlalchemy import text

from app.core import integrations, sysconfig
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.core.logging import get_logger
from app.dwh.dates import today_tashkent
from app.etl.askue.live import GesLiveClient, LiveError
from app.etl.cbu.client import cbu_probe
from app.etl.hr.client import HrApiClient, HrApiError, ca_context
from app.etl.hr.source import STRUCTURE_PATH
from app.etl.notify import smtp_probe
from app.etl.onec.client import OneCCaError, OneCClient, OneCError, OneCUnavailableError
from app.etl.onec.probe import onec_probe
from app.etl.onec.sklad import sklad_config
from app.etl.telegram import telegram_probe
from app.etl.types import ConnectorUnavailableError

log = get_logger("ugekazna.probes")


def hr_probe(transport: httpx.BaseTransport | None = None) -> str:
    """HR API: tuzilma so'rovi (shaxsiy ma'lumotsiz). Faqat xavfsiz kod."""
    with get_engine("app").connect() as conn:
        base = str(sysconfig.current(conn, "hr.base_url"))
        key = integrations.secret(conn, "hr.api_key")
    if not base or not key:
        return "not_configured"
    settings = get_settings()
    try:
        client = HrApiClient(base, key, verify=ca_context(settings.hr_ca_file),
                             proxy=settings.egress_proxy, transport=transport)
    except ConfigError:
        return "not_configured"
    try:
        client.get(STRUCTURE_PATH, {"include_empty": "false"})
    except ConnectorUnavailableError as exc:
        text_ = str(exc)
        return "timeout" if "тайм-аут" in text_ else (
            "tls_failed" if "SSL" in text_ or "Certificate" in text_ else (
                "http_error" if "HTTP" in text_ else "connect_failed"))
    except HrApiError as exc:
        return "auth_failed" if "доступ запрещён" in str(exc) else "format_error"
    finally:
        client.close()
    return "ok"


def _unavailable_code(exc: ConnectorUnavailableError) -> str:
    return "timeout" if "тайм-аут" in str(exc) else "connect_failed"


def askue_live_probe() -> str:
    """Jonli quvvat manbasi: javob olinadi va tuzilmasi tekshiriladi (yozuvsiz)."""
    with get_engine("app").connect() as conn:
        url = str(sysconfig.current(conn, "askue.live_url"))
    if not url:
        return "not_configured"
    try:
        client = GesLiveClient(url, proxy=get_settings().egress_proxy)
    except ConfigError:
        return "not_configured"
    try:
        client.fetch()
    except ConnectorUnavailableError as exc:
        return _unavailable_code(exc)
    except LiveError as exc:
        return "http_error" if "HTTP" in str(exc) else "format_error"
    finally:
        client.close()
    return "ok"


def onec_sklad_probe() -> str:
    """1C ombor servisi: bitta kunlik /materials so'rovi (hisob ma'lumoti panelda)."""
    with get_engine("app").connect() as conn:
        if not integrations.configured(conn, "onec_sklad"):
            return "not_configured"
        config = sklad_config(conn)
        orgs = sysconfig.current(conn, "onec.orgs")
    try:
        client = OneCClient(config)
    except OneCCaError:
        return "ca_invalid"
    except ConfigError:
        return "insecure_refused"
    today = today_tashkent().isoformat()
    try:
        client.post("/materials", {"date_from": today, "date_to": today,
                                   "org_uid": orgs[0]["org_uid"] if orgs else ""})
    except (OneCError, OneCUnavailableError) as exc:
        return exc.code
    finally:
        client.close()
    return "ok"


PROBES: dict[str, Callable[[], str]] = {
    "smtp": smtp_probe, "onec": onec_probe, "hr": hr_probe, "telegram": telegram_probe,
    "cbu": cbu_probe, "askue_live": askue_live_probe, "onec_sklad": onec_sklad_probe}

_BATCH = 5


def process_integration_checks() -> int:
    with get_engine("app").begin() as conn:
        conn.execute(text("UPDATE core.integration_checks SET status = 'failed', code = 'timeout', "
                          "finished_at = now() WHERE status = 'running' "
                          "AND requested_at < now() - interval '5 minutes'"))
        rows = conn.execute(text(
            "UPDATE core.integration_checks SET status = 'running' WHERE id IN ("
            "SELECT id FROM core.integration_checks WHERE status = 'pending' ORDER BY id "
            "LIMIT :n FOR UPDATE SKIP LOCKED) RETURNING id, name"), {"n": _BATCH}).all()
    for row in rows:
        probe = PROBES.get(row.name)
        try:
            code = probe() if probe is not None else "not_supported"
        except Exception as exc:
            log.error("integration_probe_failed", name=row.name, error=type(exc).__name__)
            code = "error"
        with get_engine("app").begin() as conn:
            conn.execute(text("UPDATE core.integration_checks SET status = :s, code = :c, "
                              "finished_at = now() WHERE id = :i"),
                         {"s": "ok" if code == "ok" else "failed", "c": code[:32], "i": row.id})
        log.info("integration_checked", name=row.name, code=code)
    return len(rows)
