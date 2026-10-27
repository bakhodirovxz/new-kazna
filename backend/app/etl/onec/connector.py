"""1C konnektorlari uchun umumiy yordamchilar: tashkilot ↔ filial, barqaror kod, so'm → mln."""

from __future__ import annotations

import hashlib
from decimal import ROUND_HALF_EVEN, Decimal

from app.core.setting_types import OneCOrg as OrgMap

__all__ = ["OrgMap", "stable_code", "to_mln"]
_MLN = Decimal(1_000_000)
_CENTS = Decimal("0.01")


def stable_code(prefix: str, *parts: str) -> str:
    """Manba kodi yo'q bo'lsa — qismlardan barqaror (qayta yuklashda o'zgarmas) kod, ≤ 32 belgi."""
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]
    return f"{prefix}{digest}"[:32]


def to_mln(amount: Decimal) -> Decimal:
    """So'm → mln so'm (numeric(20,2))."""
    return (amount / _MLN).quantize(_CENTS, rounding=ROUND_HALF_EVEN)
