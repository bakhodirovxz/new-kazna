import contextlib
import io
import json

import pytest
from fastapi.testclient import TestClient

from app import devtools
from app.main import create_app


def _cookie(entry: dict[str, object]) -> dict[str, str]:
    return {"Cookie": f"__Host-ugk_session={entry['token']}"}


def _seed(users: int) -> list[dict[str, object]]:
    # capsys emas: create_app() structlog'ni sys.stdout'ga bog'laydi (yopiq capsys buzadi).
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert devtools.main(["seed-load", "--users", str(users)]) == 0
    return json.loads(out.getvalue().strip().splitlines()[-1])


def test_seed_load_refuses_outside_dev_and_test(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENV", "prod")
    assert devtools.main(["seed-load", "--users", "2"]) == 2
    assert "Rad etildi" in capsys.readouterr().out


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
