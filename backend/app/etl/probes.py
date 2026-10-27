"""Integratsiya ulanish tekshiruvlari navbati (worker, egress bor joyda).

Natija — faqat xavfsiz kod; istisno matni saqlanmaydi (unda sir bo'lishi mumkin).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from sqlalchemy import text

from app.core import integrations, sysconfig
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.core.logging import get_logger
from app.etl.askue.live import GesLiveClient, LiveError
from app.etl.notify import smtp_probe
from app.etl.onec.client import OneCClient, OneCError, OneCFormatError, verify_setting
from app.etl.types import ConnectorUnavailableError

log = get_logger("ugekazna.probes")


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
        base_url = str(sysconfig.current(conn, "onec_sklad.base_url"))
        username = integrations.secret(conn, "onec_sklad.username")
        password = integrations.secret(conn, "onec_sklad.password")
        orgs = sysconfig.current(conn, "onec.orgs")
    settings = get_settings()
    try:
        client = OneCClient(base_url, username, password,
                            verify=verify_setting(settings.onec_ca_file),
                            allow_http=settings.onec_allow_http)
    except ConfigError:
        return "not_configured"
    today = date.today().isoformat()  # noqa: DTZ011 — probe: sana ahamiyatsiz, javob shakli muhim
    try:
        client.post("/materials", {"date_from": today, "date_to": today,
                                   "org_uid": orgs[0]["org_uid"] if orgs else ""})
    except ConnectorUnavailableError as exc:
        return _unavailable_code(exc)
    except OneCFormatError:
        return "format_error"
    except OneCError as exc:
        return "auth_failed" if "доступ" in str(exc) else "http_error"
    finally:
        client.close()
    return "ok"


PROBES: dict[str, Callable[[], str]] = {
    "smtp": smtp_probe, "askue_live": askue_live_probe, "onec_sklad": onec_sklad_probe}
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
