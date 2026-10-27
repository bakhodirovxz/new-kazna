"""2FA ulashni taklif qilish holati (buyurtmachi qarori 27.10.2026: 2FA majburiy emas).

"Rad etilgan" belgisi alohida ustunda emas, audit jurnalidagi `auth.mfa_offer_dismissed`
hodisasida saqlanadi (migratsiyasiz — S1 0009/0010 zanjirini buzmaslik uchun). Cheklov:
jurnal saqlash muddati (`retention.audit_months`) o'tgach hodisa o'chadi va taklif qaytadi.
Rad etish faqat oxirgi parol o'rnatilgandan KEYIN sanaladi: parol almashganda (o'zi yoki
administrator tomonidan) taklif bir marta qaytadi — bu e2e-seed'ni ham takrorlanuvchan qiladi.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.service import AuditAction
from app.core import sysconfig


def mfa_offer_pending(db: Session, user_id: int, mfa_enabled: bool) -> bool:
    if mfa_enabled or sysconfig.value("security.mfa_required"):
        return False  # ulangan yoki majburiy (majburiy bo'lsa kirishda o'zi so'raladi)
    dismissed = db.execute(
        text(
            "SELECT 1 FROM core.audit_log a JOIN core.users u ON u.id = a.user_id "
            "WHERE a.user_id = :u AND a.action = :a AND a.ts >= u.password_changed_at LIMIT 1"
        ),
        {"u": user_id, "a": str(AuditAction.MFA_OFFER_DISMISSED)},
    ).first()
    return dismissed is None
