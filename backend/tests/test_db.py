from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.db import apply_rls, get_engine, new_session
from app.main import create_app


@pytest.fixture
def rls_probe() -> Iterator[None]:
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS core.rls_probe"))
        conn.execute(text("CREATE TABLE core.rls_probe (id int, branch_id int NOT NULL)"))
        conn.execute(text("INSERT INTO core.rls_probe VALUES (1, 0), (2, 1), (3, 2)"))
        conn.execute(text("ALTER TABLE core.rls_probe ENABLE ROW LEVEL SECURITY"))
        conn.execute(text("ALTER TABLE core.rls_probe FORCE ROW LEVEL SECURITY"))
        conn.execute(
            text("CREATE POLICY p ON core.rls_probe USING (core.rls_branch_ok(branch_id))")
        )
        conn.execute(text("GRANT SELECT ON core.rls_probe TO ugk_app"))
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DROP TABLE core.rls_probe"))


def _visible(scope: frozenset[int] | str | None) -> list[int]:
    with new_session() as s:
        if scope != "unset":
            apply_rls(s, scope)  # type: ignore[arg-type]
        return sorted(s.execute(text("SELECT id FROM core.rls_probe")).scalars())


@pytest.mark.usefixtures("rls_probe")
def test_rls_scopes() -> None:
    assert _visible("unset") == []
    assert _visible(frozenset()) == []
    assert _visible(frozenset({1})) == [2]
    assert _visible(frozenset({1, 2})) == [2, 3]
    assert _visible(None) == [1, 2, 3]


@pytest.mark.usefixtures("rls_probe")
def test_rls_setting_is_transaction_local() -> None:
    with new_session() as s:
        apply_rls(s, None)
        assert len(s.execute(text("SELECT id FROM core.rls_probe")).all()) == 3
        s.commit()
        assert s.execute(text("SELECT id FROM core.rls_probe")).all() == []


def test_app_role_cannot_create_tables() -> None:
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("CREATE TABLE core.hack (id int)"))


def test_app_role_has_no_bypassrls() -> None:
    with new_session() as s:
        row = s.execute(
            text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")
        ).one()
    assert row == (False, False)


def test_readyz_reports_db() -> None:
    with TestClient(create_app(), base_url="https://testserver") as client:
        response = client.get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["db"] is True
