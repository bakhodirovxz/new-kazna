import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def test_get_db_only_via_db_alias() -> None:
    # hotfix f052efd: boshqa scope'dagi Depends(get_db) ikkinchi sessiya beradi,
    # RLS konteksti yo'qoladi.
    offenders = sorted(
        str(p.relative_to(APP))
        for p in APP.rglob("*.py")
        if p.relative_to(APP).as_posix() != "core/db.py"
        and "Depends(get_db" in p.read_text("utf-8")
    )
    assert offenders == []


_MANUAL_FACTS = (
    "balance|payment_plan|debt|target_funds|loan_schedule|generation|energy_sales|investment|hr"
    "|object_stage"
)
_FACT_READ = re.compile(rf"dwh\.fact_({_MANUAL_FACTS})\b")
# Jadvalni to'g'ridan-to'g'ri nomlaydigan yagona ruxsat etilgan modullar (reyestr, partitsiya).
_FACT_READ_EXEMPT = {"dwh/targets.py", "dwh/partitions.py"}
_MARK = "# manual-ok"


def _aggregate_modules() -> list[Path]:
    """Agregat, finmodel va sifat kodi KODDAN topiladi (S2-S5 qo'shgan yangi modullar ham
    avtomatik tushadi): app/dwh/*.py, app/finmodel/**, app/etl/quality.py."""
    mods = list((APP / "dwh").rglob("*.py"))
    mods += list((APP / "finmodel").rglob("*.py")) if (APP / "finmodel").is_dir() else []
    mods.append(APP / "etl" / "quality.py")
    return sorted(m for m in mods if m.relative_to(APP).as_posix() not in _FACT_READ_EXEMPT)


def test_manual_facts_read_via_effective_views() -> None:
    mods = _aggregate_modules()
    names = {m.name for m in mods}
    assert {"aggregates.py", "treasury_aggregates.py", "quality.py"} <= names  # ko'r emasligi
    offenders = [
        f"{m.relative_to(APP).as_posix()}:{n}: {line.strip()[:80]}"
        for m in mods
        for n, line in enumerate(m.read_text("utf-8").splitlines(), start=1)
        if _FACT_READ.search(line) and _MARK not in line
    ]
    assert offenders == [], "agregat/sifat kodi dwh.fact_* ni emas, dwh.<x>_effective ni o'qisin"


def test_effective_rule_catches_a_violation() -> None:
    bad = "SELECT 1 FROM dwh.fact_balance fb"
    assert _FACT_READ.search(bad) and not _FACT_READ.search("FROM dwh.balance_effective")
    assert not _FACT_READ.search("FROM dwh.fact_cashflow")  # cashflow -- o'zgarishsiz
