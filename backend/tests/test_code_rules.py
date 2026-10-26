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
