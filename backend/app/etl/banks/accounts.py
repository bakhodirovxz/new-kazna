"""Hisob raqami → `banks.accounts` yozuvi. Kod — HMAC (blind_index_key, "account"): ochiq raqam
sozlamada ham, jurnalda ham saqlanmaydi; dim_bank.account_bidx bilan bir xil kalit va yorliq."""

from __future__ import annotations

from collections.abc import Sequence

from app.core.config import get_settings
from app.core.crypto import blind_index
from app.etl.banks.models import normalize_account
from app.etl.banks.registry import BankAccount


def account_code(account: str, key: bytes | None = None) -> str:
    secret = key if key is not None else get_settings().key_bytes("blind_index_key")
    return "BA-" + blind_index(secret, "account", normalize_account(account)).hex()[:16]


class AccountIndex:
    def __init__(self, accounts: Sequence[BankAccount], key: bytes | None = None) -> None:
        self._by_code = {a.code: a for a in accounts}
        self._key = key if key is not None else get_settings().key_bytes("blind_index_key")

    def resolve(self, account: str) -> BankAccount | None:
        return self._by_code.get(account_code(account, self._key))
