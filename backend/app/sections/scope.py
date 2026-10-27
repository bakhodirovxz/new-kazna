"""Qaysi agregat qatorlari o'qiladi (spec 6): `br` → shu filial; `scope_all` → jami (branch_id = 0);
cheklangan doira → o'z filiallari yig'indisi (RLS faqat ularni ko'rsatadi, 0-qator ko'rinmaydi)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BranchSel:
    br: int | None
    all_scope: bool

    @classmethod
    def of(cls, br: int | None, branch_ids: frozenset[int] | None) -> BranchSel:
        return cls(br, branch_ids is None)

    def total(self, col: str = "branch_id") -> tuple[str, dict[str, Any]]:
        """Jami ko'rsatkichlar uchun shart (yig'indi shu qatorlar bo'yicha olinadi)."""
        if self.br is not None:
            return f"{col} = :sel_br", {"sel_br": self.br}
        if self.all_scope:
            return f"{col} = 0", {}
        return f"{col} <> 0", {}

    def rows(self, col: str = "branch_id") -> tuple[str, dict[str, Any]]:
        """Filiallar kesimidagi jadvallar uchun shart (0-qator hech qachon)."""
        if self.br is not None:
            return f"{col} = :sel_br", {"sel_br": self.br}
        return f"{col} <> 0", {}
