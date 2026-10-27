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
from app.etl.hr.client import HrApiClient, HrApiError, ca_context
from app.etl.notify import smtp_probe
from app.etl.types import ConnectorUnavailableError

log = get_logger("ugekazna.probes")


def hr_probe(transport: httpx.BaseTransport | None = None) -> str:
    """HR API: faqat login (ma'lumot so'ralmaydi). Faqat xavfsiz kod qaytadi (U8/U9)."""
    with get_engine("app").connect() as conn:
        base = str(sysconfig.current(conn, "hr.base_url"))
        user, password = integrations.secret(conn, "hr.username"), integrations.secret(
            conn, "hr.password")
    if not base or not user or not password:
        return "not_configured"
    settings = get_settings()
    try:
        client = HrApiClient(base, user, password, verify=ca_context(settings.hr_ca_file),
                             proxy=settings.egress_proxy, transport=transport)
    except ConfigError:
        return "not_configured"
    try:
        client.login()
    except ConnectorUnavailableError as exc:
        text_ = str(exc)
        return "timeout" if "тайм-аут" in text_ else (
            "tls_failed" if "SSL" in text_ or "Certificate" in text_ else (
                "http_error" if "HTTP" in text_ else "connect_failed"))
    except HrApiError as exc:
        return "auth_failed" if "вход не выполнен" in str(exc) else "format_error"
    finally:
        client.close()
    return "ok"


PROBES: dict[str, Callable[[], str]] = {"smtp": smtp_probe, "hr": hr_probe}
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
