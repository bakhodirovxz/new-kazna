"""«Ввод данных» testlari uchun yordamchilar (sintetik qiymatlar, hisob raqami faqat testda)."""

from __future__ import annotations

import itertools
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.core.db import get_engine

_n = itertools.count(1)


def branch_code(branch_id: int) -> str:
    with get_engine("migrator").begin() as conn:
        conn.execute(text("SELECT set_config('app.scope_all', 'on', true)"))
        return str(conn.execute(text("SELECT code FROM dwh.dim_branch WHERE branch_id = :b"),
                                {"b": branch_id}).scalar_one())


def account_number(tag: int | None = None) -> str:
    """Har chaqiruvda yangi 20 xonali sinov hisobi."""
    return f"20208{(tag if tag is not None else next(_n)) + 10**14:015d}"[:20]


def bank_account_item(branch_id: int = 1, *, number: str | None = None) -> dict[str, Any]:
    return {
        "branch_code": branch_code(branch_id),
        "bank_name": "Асакабанк",
        "currency": "UZS",
        "account_number": number or account_number(),
    }


def balance_item(
    code: str, day: str | date, value: str | Decimal, branch_id: int = 1
) -> dict[str, Any]:
    return {"branch_code": branch_code(branch_id), "bank_code": code,
            "date": day if isinstance(day, str) else day.isoformat(), "balance": str(value)}


def plan_item(
    item_code: str, month: str, amount: str | Decimal, branch_id: int = 1
) -> dict[str, Any]:
    return {"branch_code": branch_code(branch_id), "item_code": item_code,
            "date": month, "amount": str(amount)}


def seed_dwh_bank(code: str, name: str = "Тест-банк") -> None:
    with get_engine("migrator").begin() as conn:
        conn.execute(text(
            "INSERT INTO dwh.dim_bank (code, bank_name, currency) VALUES (:c, :n, 'UZS') "
            "ON CONFLICT (code) DO NOTHING"), {"c": code, "n": name})


def migrator_sql(sql: str, **params: Any) -> list[tuple[Any, ...]]:
    """Egasi sifatida (FORCE RLS uchun scope_all bilan) -- faqat test tayyorgarligi/tekshiruvi."""
    with get_engine("migrator").begin() as conn:
        conn.execute(text("SELECT set_config('app.scope_all', 'on', true)"))
        res = conn.execute(text(sql), params)
        return [tuple(r) for r in res.all()] if res.returns_rows else []
