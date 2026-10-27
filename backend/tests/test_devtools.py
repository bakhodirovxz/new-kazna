import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import devtools
from app.auth.models import PositionBranch, User
from app.auth.service import totp_aad
from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import new_session
from app.main import create_app


@pytest.mark.parametrize("env", ["prod", "staging", ""])
def test_refuses_outside_dev_and_test(
    env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENV", env)
    assert devtools.main(["seed-e2e"]) == 2
    assert "Rad etildi" in capsys.readouterr().out


def test_refuses_when_env_is_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Settings.env standart qiymati "dev": aniq ENV bo'lmasa fail-open bo'lmasligi kerak.
    monkeypatch.delenv("ENV", raising=False)
    def boom() -> None:
        raise AssertionError("bootstrap_runtime chaqirilmasligi kerak")

    monkeypatch.setattr(devtools, "bootstrap_runtime", boom)
    assert devtools.main(["seed-e2e"]) == 2
    assert "Rad etildi" in capsys.readouterr().out


def test_seed_is_idempotent_and_resets_state() -> None:
    assert devtools.main(["seed-e2e"]) == 0
    with new_session() as db:
        admin = db.execute(select(User).where(User.username == "e2e_admin_1440")).scalar_one()
        admin.failed_logins = 4
        admin.totp_last_step = 999_999_999
        admin.is_active = False
        db.commit()

    assert devtools.main(["seed-e2e"]) == 0
    with new_session() as db:
        names = [s.username for s in devtools.E2E_USERS]
        rows = db.execute(select(User).where(User.username.in_(names))).scalars()
        users = {u.username: u for u in rows}
        assert set(users) == set(names)
        admin = users["e2e_admin_1440"]
        assert admin.is_active and admin.failed_logins == 0 and admin.totp_last_step is None
        assert admin.totp_enabled and admin.totp_secret_enc is not None
        secret = keystore.decrypt_str(Purpose.MFA, admin.totp_secret_enc, totp_aad(admin.id))
        assert secret == devtools.E2E_TOTP_SECRET
        new = users["e2e_new"]
        assert new.must_change_password and not new.totp_enabled and new.totp_secret_enc is None
        skip = users["e2e_skip"]
        assert not skip.must_change_password and not skip.totp_enabled
        manual = {f"e2e_{k}_{w}" for k in ("maker", "checker") for w in ("390", "1024", "1440")}
        assert manual <= set(users)
        branch_position = users["e2e_branch"].position_id
        stmt = select(PositionBranch.branch_id).where(PositionBranch.position_id == branch_position)
        branches = db.execute(stmt).scalars().all()
        assert list(branches) == [3]


def test_seeded_admin_can_sign_in_with_the_known_totp_secret() -> None:
    assert devtools.main(["seed-e2e"]) == 0
    with TestClient(create_app(), base_url="https://testserver") as client:
        creds = {"username": "e2e_admin_1024", "password": devtools.E2E_PASSWORD}
        r = client.post("/api/v1/auth/login", json=creds)
        assert r.status_code == 200
        assert r.json()["next"] == "mfa_verify"
        code = pyotp.TOTP(devtools.E2E_TOTP_SECRET).now()
        body = {"mfa_token": r.json()["mfa_token"], "code": code}
        r = client.post("/api/v1/auth/2fa/verify", json=body)
        assert r.status_code == 200
        assert "admin:users" in r.json()["permissions"]
