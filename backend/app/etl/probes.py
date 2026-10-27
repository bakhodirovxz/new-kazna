"""Integratsiya ulanish tekshiruvlari navbati (worker, egress bor joyda).

Natija — faqat xavfsiz kod; istisno matni saqlanmaydi (unda sir bo'lishi mumkin).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text

from app.core.db import get_engine
from app.core.logging import get_logger
from app.etl.cbu.client import cbu_probe
from app.etl.notify import smtp_probe
from app.etl.telegram import telegram_probe

log = get_logger("ugekazna.probes")
PROBES: dict[str, Callable[[], str]] = {"smtp": smtp_probe, "telegram": telegram_probe,
                                         "cbu": cbu_probe}
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
