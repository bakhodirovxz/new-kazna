"""Ishga tushishdagi idempotent tayyorgarlik. Bir nechta worker parallel chaqirsa ham xavfsiz."""

from __future__ import annotations

from sqlalchemy import text

from app.auth.seed import sync_reference
from app.core import keystore
from app.core.config import get_settings
from app.core.db import get_engine, new_session


def bootstrap_runtime() -> None:
    kek = get_settings().key_bytes("master_kek")
    with get_engine("app").begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_bootstrap'))"))
        keystore.ensure_keys(conn, kek)
    keystore.invalidate_keyring()
    keystore.get_keyring()  # noto'g'ri master_kek ishga tushishdayoq aniqlansin
    with new_session() as db:
        sync_reference(db)
        db.commit()
