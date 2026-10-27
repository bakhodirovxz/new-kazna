import contextlib
import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import devtools
from app.core.db import get_engine
from app.main import create_app


def _cookie(entry: dict[str, object]) -> dict[str, str]:
    return {"Cookie": f"__Host-ugk_session={entry['token']}"}


def _seed(users: int) -> list[dict[str, object]]:
    # capsys emas: create_app() structlog'ni sys.stdout'ga bog'laydi (yopiq capsys buzadi).
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert devtools.main(["seed-load", "--users", str(users)]) == 0
    return json.loads(out.getvalue().strip().splitlines()[-1])


def _load_user_count() -> int:
    with get_engine("migrator").connect() as conn:
        return int(conn.execute(
            text("SELECT count(*) FROM core.users WHERE starts_with(username, 'load_')")
        ).scalar_one())


@pytest.mark.parametrize("env", ["prod", None])
@pytest.mark.parametrize("extra", [[], ["--purge"]])
def test_seed_load_refuses_outside_dev_and_test(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    env: str | None, extra: list[str],
) -> None:
    """ENV=prod yoki belgilanmagan: seed ham, purge ham DB'ga tegmaydi."""
    devtools.purge_load()
    _seed(1)
    before = _load_user_count()
    if env is None:
        monkeypatch.delenv("ENV", raising=False)
    else:
        monkeypatch.setenv("ENV", env)
    assert devtools.main(["seed-load", "--users", "2", *extra]) == 2
    out = capsys.readouterr().out
    assert "Rad etildi" in out and f"ENV={env or 'belgilanmagan'}" in out
    assert _load_user_count() == before == 1


def test_seed_load_purge_removes_users_sessions_and_positions() -> None:
    data = _seed(3)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert devtools.main(["seed-load", "--purge"]) == 0
    assert "O'chirildi: 3 ta" in out.getvalue()
    assert _load_user_count() == 0
    with get_engine("migrator").connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM core.positions WHERE starts_with(code, 'e2e_load_')"
        )).scalar_one() == 0
        assert conn.execute(text(
            "SELECT count(*) FROM core.sessions s LEFT JOIN core.users u ON u.id = s.user_id "
            "WHERE u.id IS NULL")).scalar_one() == 0
    with TestClient(create_app(), base_url="https://testserver") as client:
        assert client.get("/api/v1/auth/me", headers=_cookie(data[0])).status_code == 401


def test_seed_load_sessions_work_and_respect_scope() -> None:
    data = _seed(3)
    assert [d["username"] for d in data] == ["load_001", "load_002", "load_003"]
    assert data[0]["branches"] == [] and data[2]["branches"] == [3]
    with TestClient(create_app(), base_url="https://testserver") as client:
        me = client.get("/api/v1/auth/me", headers=_cookie(data[0]))
        assert me.status_code == 200
        assert me.json()["username"] == "load_001"
        branches = client.get("/api/v1/meta/branches", headers=_cookie(data[2]))
        assert branches.status_code == 200
        assert [b["id"] for b in branches.json()] == [3]


def test_seed_load_is_idempotent_and_revokes_old_sessions() -> None:
    first = _seed(2)
    second = _seed(2)
    with TestClient(create_app(), base_url="https://testserver") as client:
        assert client.get("/api/v1/auth/me", headers=_cookie(first[0])).status_code == 401
        assert client.get("/api/v1/auth/me", headers=_cookie(second[0])).status_code == 200


def test_seed_load_rejects_bad_count() -> None:
    with pytest.raises(SystemExit):
        devtools.main(["seed-load", "--users", "0"])
    with pytest.raises(SystemExit):
        devtools.main(["seed-load", "--users", "501"])
