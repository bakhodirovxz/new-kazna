"""Manba identifikatorlaridan barqaror kodlar va pul birliklari (S4; S1 onec konnektori
shu nomlarni `app.etl.onec.connector` da beradi — integrator birlashtiradi)."""

from __future__ import annotations

import hashlib
from decimal import ROUND_HALF_UP, Decimal

from app.core.setting_types import normalize_org as normalize_name

__all__ = ["normalize_name", "stable_code", "to_mln"]


def stable_code(prefix: str, value: str) -> str:
    """`prefix` + normallashtirilgan qiymat xeshi (o'lcham `code` ustuni ochiq matn)."""
    return prefix + hashlib.sha256(normalize_name(value).encode()).hexdigest()[:12].upper()


def to_mln(uzs: Decimal | int | float | str) -> Decimal:
    """So'm -> mln so'm, 2 kasr."""
    return (Decimal(str(uzs)) / Decimal(1_000_000)).quantize(Decimal("0.01"), ROUND_HALF_UP)
