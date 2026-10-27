"""Bo'lim endpointlari uchun umumiy filtrlar: br, per, «bugun» (testlarda almashtiriladi)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query

from app.auth.context import Ctx
from app.dwh.dates import today_tashkent
from app.sections.period import ReportPeriod, normalize_per, resolve_period
from app.sections.scope import BranchSel

PER_PATTERN = r"^(ytd|q[1-4]|m(0[1-9]|1[0-2])|0[1-9]|1[0-2])$"  # oxirgi ikkitasi — `05` alias


def get_today() -> date:
    return today_tashkent()


Today = Annotated[date, Depends(get_today)]


@dataclass(frozen=True, slots=True)
class SectionQuery:
    br: int | None
    per: str
    today: date
    branch_ids: frozenset[int] | None

    @property
    def cache_filters(self) -> dict[str, Any]:
        # Davr sanaga bog'liq — "bugun" ham kesh kalitiga kiradi.
        return {"br": self.br, "per": self.per, "today": self.today.isoformat()}

    def period(self) -> ReportPeriod:
        return resolve_period(self.per, self.today)

    def sel(self) -> BranchSel:
        return BranchSel.of(self.br, self.branch_ids)


def section_query(
    ctx: Ctx,
    today: Today,
    br: Annotated[int | None, Query(ge=1)] = None,
    per: Annotated[str, Query(pattern=PER_PATTERN)] = "ytd",
) -> SectionQuery:
    per = normalize_per(per)
    ctx.assert_branch(br)  # doiradan tashqari → 403 scope_violation + audit (1-qavat RLS)
    resolve_period(per, today)  # joriy yilda yo'q davr → 422
    return SectionQuery(br, per, today, ctx.branch_ids)


SQ = Annotated[SectionQuery, Depends(section_query)]
