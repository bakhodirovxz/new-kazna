"""Shaxsiy va bank rekvizitlari detektori (S5 spec 4.2) — AI kontekstiga va savolga qo'llanadi.

Kalitlar: ФИО, INN/ПИНФЛ, pasport, hisob, telefon, manzil, kontragent/yetkazib beruvchi, shifrlangan
ustunlar. Qiymatlar: 9 xonali INN, 14 xonali ПИНФЛ, 16–20 xonali hisob/karta, pasport seriyasi.
Kontekstdagi summalar mln so'mda va 2 xonagacha yaxlitlanadi — 9+ xonali butun son bo'lmaydi.
"""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEY_RE = re.compile(
    r"(^|_)(inn|pinfl|passport|iban|mfo|fio|surname|phone|email|address|contact)(_|$)"
    r"|account|full_?name|first_?name|last_?name|middle_?name|responsible|person"
    r"|counterpart|supplier|purpose|signed|engineer|_enc$|_bidx$|^cp_",
    re.IGNORECASE)

SENSITIVE_VALUE_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("inn", re.compile(r"(?<!\d)\d{9}(?!\d)")),
    ("pinfl", re.compile(r"(?<!\d)\d{14}(?!\d)")),
    ("account", re.compile(r"(?<!\d)\d{16,20}(?!\d)")),
    ("passport", re.compile(r"(?<![A-Za-z])[A-Z]{2}\s?\d{7}(?!\d)")),
)


def find_sensitive_text(value: str) -> list[str]:
    return [name for name, pattern in SENSITIVE_VALUE_RES if pattern.search(value)]


def find_sensitive_keys(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if SENSITIVE_KEY_RE.search(str(key)):
                found.append(str(key))
            found.extend(find_sensitive_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(find_sensitive_keys(item))
    return found
