import pytest

from app.auth.permissions import ADMIN_ROLE, PERMISSIONS, ROLE_SEEDS, Section, data_perm
from app.core import ratelimit, sysconfig


def test_data_perms_generated_and_not_given_to_admin() -> None:
    perms = {data_perm(s, a) for s in (Section.KAZNA, Section.KADRY) for a in ("write", "approve")}
    assert perms <= set(PERMISSIONS)
    admin = next(r for r in ROLE_SEEDS if r.code == ADMIN_ROLE)
    assert not any(p.startswith("data:") for p in admin.permissions)


def test_seeded_roles() -> None:
    by = {r.code: r.permissions for r in ROLE_SEEDS}
    assert "data:kazna:write" in by["spec_kazna"] and "data:kazna:approve" not in by["spec_kazna"]
    assert {"data:kazna:approve", "data:kadry:approve"} <= by["nach_otdela"]
    assert not any(p.endswith(":approve") for p in by["economist_filiala"])


def test_locked_through_validation() -> None:
    d = sysconfig.REGISTRY["manual.locked_through"]
    assert d.validate("") == "" and d.validate("2026-08") == "2026-08"
    for bad in ("2026-13", "2026-8", "202608", "2026-00"):
        with pytest.raises(ValueError):
            d.validate(bad)
    assert d.guarded


def test_data_write_limit_only_tightens(setting) -> None:  # type: ignore[no-untyped-def]
    assert ratelimit.data_write_per_user().events == 60
    d = sysconfig.REGISTRY["ratelimit.data_write_per_min"]
    with pytest.raises(ValueError):
        d.validate(61)
    setting("ratelimit.data_write_per_min", 10)
    assert ratelimit.data_write_per_user().events == 10

