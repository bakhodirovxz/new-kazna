"""«Ввод данных» testlari uchun yordamchilar (sintetik qiymatlar, hisob raqami faqat testda)."""

from __future__ import annotations

import itertools
import json
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text

from app.auth.context import AuthContext, build_context
from app.auth.models import User
from app.core.db import apply_rls, get_engine, new_session
from app.core.request_meta import ClientMeta
from tests.helpers import SeedUser

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


# --- servis testlari: haqiqiy AuthContext + RLS sessiya (har chaqiruv alohida tranzaksiya) ---
META = ClientMeta(ip="127.0.0.1", ua="pytest", request_id="req-manual")


def ctx_of(user: SeedUser) -> AuthContext:
    with new_session() as s:
        row = s.execute(select(User).where(User.id == user.id)).scalar_one()
        return build_context(s, row, uuid.uuid4(), datetime.now(UTC))


def run(ctx: AuthContext, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Servis funksiyasini foydalanuvchi doirasidagi (RLS) yangi sessiyada chaqiradi."""
    with new_session() as s:
        apply_rls(s, ctx.branch_ids)
        try:
            return fn(s, ctx, META, *args, **kwargs)
        finally:
            s.rollback()


def read(ctx: AuthContext, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Faqat o'qish servislari (meta yo'q)."""
    with new_session() as s:
        apply_rls(s, ctx.branch_ids)
        try:
            return fn(s, ctx, *args, **kwargs)
        finally:
            s.rollback()


def audit_rows(action: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT action, result, user_id, object_id, details FROM core.audit_log"
    sql += " WHERE action = :a" if action else " WHERE action LIKE 'data.%'"
    sql += " ORDER BY id"
    return [
        {"action": r[0], "result": r[1], "user_id": r[2], "object_id": r[3], "details": r[4]}
        for r in migrator_sql(sql, **({"a": action} if action else {}))
    ]


def audit_dump() -> str:
    return json.dumps([r["details"] for r in audit_rows()], ensure_ascii=False, default=str)


def make_role_user(
    perms: set[str], *, branch_ids: tuple[int, ...] = (), scope_all: bool = False
) -> SeedUser:
    """Maxsus ruxsatli rol va lavozim (masalan, filialga cheklangan tasdiqlovchi)."""
    from app.auth.models import Role, RolePermission
    from tests.helpers import create_user

    code = f"t_{uuid.uuid4().hex[:10]}"
    with new_session() as s:
        role = Role(code=code, name=code, scope_all=scope_all, is_system=False)
        s.add(role)
        s.flush()
        for perm in sorted(perms):
            s.add(RolePermission(role_id=role.id, permission_code=perm))
        s.commit()
    return create_user(code, branch_ids=branch_ids)
