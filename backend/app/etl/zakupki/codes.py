"""Xarid holatlari va usullari — yagona manba (migratsiya 0016 CHECK'lari shu qiymatlar bilan).

Holatlar TZ 3-bo'lim/4-bo'lim so'zlari bilan (ruscha, kichik harf); usullar — barqaror kodlar,
ekrandagi nomi METHOD_TITLES dan. Normativ kunlar — core.settings `zakupki.method_norms`.
"""

from __future__ import annotations

from app.core.setting_types import DEFAULT_METHOD_NORMS as DEFAULT_METHOD_NORMS
from app.core.setting_types import METHODS as METHODS

IN_WORK: tuple[str, ...] = ("объявлен", "на оценке")
DONE = "договор заключён"
CANCELLED = "отменён"
PLAN_STATUS = "план"
STATUSES: tuple[str, ...] = (*IN_WORK, DONE, CANCELLED, PLAN_STATUS)

PLAN_METHOD = "plan"
DIRECT = "direct"
PLAN_DOC = "procurement_plan"

METHOD_TITLES: dict[str, str] = {
    "eshop": "Электронный магазин",
    "contest": "Электронный конкурс",
    "tender": "Тендер",
    "exchange": "Биржевые торги",
    "direct": "Прямой договор",
    "other": "Прочие способы",
    "plan": "План закупок",
}

LATE_MARGIN_DAYS = 10  # TZ 4: «превышают норматив способа более чем на 10»

INDIVIDUAL_CP = "CP-FL"  # jismoniy shaxs / YaTT yetkazib beruvchi — nom saqlanmaydi (TZ 9)
INDIVIDUAL_NAME = "Физическое лицо"
