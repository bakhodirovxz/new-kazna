"""AI-анализni yoqish/o'chirish — auditlanadigan sozlama o'zgarishi (S5 spec 6), break-glass CLI.

Panel (`PUT /admin/settings/ai.enabled`, sabab + TOTP) bilan bir xil natija: versiyali sozlama
(`config_service.write_setting`) va `admin.setting.updated` auditi (`via = "cli"`, sabab —
axborot xavfsizligi xulosasi raqami). Tartib: avval commit, keyin audit.
"""

from __future__ import annotations

import sys

from app.admin.config_service import write_setting
from app.audit.service import AuditAction, AuditEvent, record
from app.core import sysconfig
from app.core.db import new_session


def set_ai_enabled(enabled: bool, reason: str) -> bool:
    with new_session() as db:
        version, before = write_setting(db, "ai.enabled", enabled, None)
        if version is None:
            return False
        db.commit()
    sysconfig.invalidate()
    record(AuditEvent(action=AuditAction.SETTING_UPDATED, object_type="setting",
                      object_id="ai.enabled",
                      details={"before": sysconfig.REGISTRY["ai.enabled"].default if before is None
                               else before, "after": enabled, "reason": reason[:200],
                               "via": "cli"}))
    return True


def ai_enable_command(state: str, reason: str) -> int:
    changed = set_ai_enabled(state == "on", reason)
    status = "yoqildi" if state == "on" else "o'chirildi"
    sys.stdout.write(f"AI-анализ {status}\n" if changed else "o'zgarish yo'q\n")
    return 0
