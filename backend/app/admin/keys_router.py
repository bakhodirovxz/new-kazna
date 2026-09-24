"""Shifrlash kalitlari holati va rotatsiyasi (admin:keys).

Rotatsiya (`POST /{purpose}/rotate`) `ugk_app` ulanishida bajariladi: bu faqat INSERT
(yangi kalit) va `status`/`retired_at` UPDATE — ikkalasi ham `ugk_app`ga ruxsat etilgan
(spec 3.5). `wrapped_key`ni bo'shatadigan operatsiyalar (eski kalitlarni retire qilish,
KEK rotatsiyasi) esa faqat operator CLI orqali, jadval egasi (`ugk_migrator`) sifatida
bajariladi — `app.cli`ga qarang.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, log_event
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose
from app.core.db import get_db
from app.core.reencrypt import reencrypt
from app.core.request_meta import Meta

router = APIRouter(prefix="/admin/keys", tags=["admin"])
DB = Annotated[Session, Depends(get_db)]
KeysAdmin = Annotated[AuthContext, Depends(require_perm(Perm.ADMIN_KEYS))]


class KeyOut(BaseModel):
    purpose: str
    version: int
    status: str
    created_at: datetime
    retired_at: datetime | None


class RotateOut(BaseModel):
    purpose: str
    version: int
    reencrypted: int


@router.get("")
def list_keys(ctx: KeysAdmin, db: DB) -> list[KeyOut]:
    rows = db.execute(
        text(
            "SELECT purpose, version, status, created_at, retired_at FROM core.crypto_keys "
            "ORDER BY purpose, version"
        )
    ).mappings()
    return [KeyOut(**row) for row in rows]


@router.post("/{purpose}/rotate")
def rotate_key(purpose: Purpose, ctx: KeysAdmin, db: DB, meta: Meta) -> RotateOut:
    kek = get_settings().key_bytes("master_kek")
    conn = db.connection()
    version = keystore.rotate(conn, kek, purpose)
    count = reencrypt(conn, keystore.load_keyring(conn, kek), purpose)
    keystore.invalidate_keyring()
    log_event(meta, AuditAction.KEY_ROTATED, user_id=ctx.user_id, object_type="key",
              object_id=purpose.value, details={"version": version, "reencrypted": count})
    return RotateOut(purpose=purpose.value, version=version, reencrypted=count)
