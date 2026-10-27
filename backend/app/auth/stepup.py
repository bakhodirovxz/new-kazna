"""Sezgir sozlama o'zgarishlarini joriy TOTP kodi bilan tasdiqlash (ASVS 3.7.1, spec 3.7).

Zaxira kodi qabul qilinmaydi (bir martalik zaxira tiklash uchun); kirishda ishlatilgan qadam
qayta qabul qilinmaydi (`totp_last_step`). Commit — chaqiruvchida (o'zgarish bilan birga).
"""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, log_event
from app.auth import totp
from app.auth.context import AuthContext
from app.auth.models import User
from app.auth.service import decrypt_totp_secret
from app.core import ratelimit
from app.core.errors import ValidationFailed
from app.core.request_meta import ClientMeta


def require_step_up(db: Session, actor: AuthContext, otp: str | None, meta: ClientMeta) -> None:
    if not otp:
        raise ValidationFailed("step_up_required", fields=["otp"])
    # A04b.R1: faqat XATO urinishlar sanaladi (muvaffaqiyatli o'zgarishlar byudjetni yemaydi;
    # qayta ishlatish totp_last_step bilan yopilgan).
    ratelimit.peek("step_up_user", str(actor.user_id), ratelimit.STEP_UP_PER_USER)
    # populate_existing: get_ctx user'ni qulfsiz yuklagan — qulfdan keyin DB qiymati o'qilsin.
    user = db.execute(
        select(User).where(User.id == actor.user_id).with_for_update()
        .execution_options(populate_existing=True)).scalar_one()
    secret = decrypt_totp_secret(user)
    step = totp.verify(secret, otp, user.totp_last_step, time.time()) if secret else None
    if step is None:
        ratelimit.check("step_up_user", str(actor.user_id), ratelimit.STEP_UP_PER_USER)
        log_event(meta, AuditAction.STEP_UP_FAILED, user_id=actor.user_id, result="fail")
        raise ValidationFailed("step_up_failed", fields=["otp"])
    user.totp_last_step = step
