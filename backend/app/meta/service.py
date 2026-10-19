"""Meta ma'lumotlari faqat pub view'lardan (RLS ostida) o'qiladi."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.meta.schemas import BranchOut


def list_branches(db: Session) -> list[BranchOut]:
    rows = db.execute(text(
        "SELECT branch_id, code, name, short_name, kind, capacity_mw, lat, lon "
        "FROM pub.branches ORDER BY sort_order, branch_id")).all()
    return [
        BranchOut(
            id=r.branch_id, code=r.code, name=r.name, short_name=r.short_name, kind=r.kind,
            is_hq=r.kind == "head",
            capacity_mw=None if r.capacity_mw is None else float(r.capacity_mw),
            lat=None if r.lat is None else float(r.lat),
            lon=None if r.lon is None else float(r.lon),
        )
        for r in rows
    ]
