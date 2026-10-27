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


# Foydalanuvchi savoli (erkin matn) uchun kengaytirilgan skaner. Kontekstga QO'LLANMAYDI:
# u yerda sana-vaqt ("2026-09-24 09:15") raqamlari yopishib yolg'on topilma beradi.
_PASSPORT_ANY_CASE = re.compile(r"(?<![A-Za-z])[A-Za-z]{2}\s?\d{7}(?!\d)")
_DIGIT_SEPARATOR = re.compile(r"(?<=\d)[ \-](?=\d)")
_PHONE = re.compile(
    r"(?<!\d)(?:\+?998[\s\-()]*\d{2}[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
    r"|\(?\d{2}\)?[\s\-]\d{3}[\s\-]\d{2}[\s\-]\d{2})(?!\d)")
_PATRONYMIC = r"(?:ович|евич|ьич|ич|овна|евна|ична|инична|оглы|кызы|угли)"
_FIO = re.compile(
    rf"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]*{_PATRONYMIC}\b"
    r"|\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.")


def find_sensitive_question(value: str) -> list[str]:
    """INN/hisob bo'shliq yoki chiziq bilan yozilsa ham, telefon, kichik harfli pasport, ФИО."""
    found = set(find_sensitive_text(value))
    found |= set(find_sensitive_text(_DIGIT_SEPARATOR.sub("", value)))
    if _PASSPORT_ANY_CASE.search(value):
        found.add("passport")
    if _PHONE.search(value):
        found.add("phone")
    if _FIO.search(value):
        found.add("fio")
    return sorted(found)


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
