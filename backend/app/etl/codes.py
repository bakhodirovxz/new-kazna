"""Tabiiy identifikatorli o'lchovlar kodi (S2 sxemasi): hisob raqami va INN kodga HMAC bilan
aylantiriladi -- kod ochiq saqlanadi, lekin raqamni qaytarib bo'lmaydi (blind_index_key)."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.crypto import blind_index

_INN_LEN = 9


def normalize_account(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def bank_account_code(account: str) -> str:
    key = get_settings().key_bytes("blind_index_key")
    return "BA-" + blind_index(key, "account", normalize_account(account)).hex()[:16]


def counterparty_code(inn: str) -> str:
    digits = normalize_account(inn)
    if len(digits) != _INN_LEN or digits != inn.strip():
        raise ValueError("inn: 9 ta raqam bo'lishi kerak")
    key = get_settings().key_bytes("blind_index_key")
    return "CP-" + blind_index(key, "inn", digits).hex()[:16]
