import base64
import os
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import cli
from app.auth.models import User
from app.core import keystore
from app.core.crypto import Purpose, blob_version
from app.core.db import get_engine, new_session
from app.core.reencrypt import retire_unused, versions_in_use
from app.main import create_app
from tests.helpers import SeedUser, login


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


def test_rotate_mfa_reencrypts_and_login_still_works(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    other = make_user("rukovodstvo")
    login(client, make_user("admin"))
    r = client.post("/api/v1/admin/keys/mfa/rotate")
    assert r.status_code == 200, r.text
    version = r.json()["version"]
    assert r.json()["reencrypted"] >= 2
    with new_session() as s:
        blob = s.execute(select(User.totp_secret_enc).where(User.id == other.id)).scalar_one()
    assert blob is not None and blob_version(blob) == version
    login(TestClient(client.app, base_url="https://testserver"), other)
    keys = client.get("/api/v1/admin/keys").json()
    mfa = [k for k in keys if k["purpose"] == "mfa"]
    assert {k["status"] for k in mfa} >= {"active", "decrypt_only"}


def test_retire_unused_respects_grace() -> None:
    with get_engine("migrator").begin() as conn:
        assert retire_unused(conn, Purpose.MFA, grace=timedelta(hours=1)) == []
        in_use = versions_in_use(conn, Purpose.MFA)
        retired = retire_unused(conn, Purpose.MFA, grace=timedelta(0))
        assert not set(retired) & in_use
        wrapped = conn.execute(
            text(
                "SELECT wrapped_key FROM core.crypto_keys "
                "WHERE purpose='mfa' AND status='retired'"
            )
        ).scalars().all()
    assert all(bytes(w) == b"" for w in wrapped)
    keystore.invalidate_keyring()


def test_rotate_unknown_purpose_is_422(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user("admin"))
    assert client.post("/api/v1/admin/keys/nope/rotate").status_code == 422


def test_non_admin_cannot_rotate(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("vnutr_kontrol"))
    assert client.post("/api/v1/admin/keys/mfa/rotate").status_code == 403


def test_openapi_available_in_dev(client: TestClient) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/auth/login" in spec["paths"]


def test_cli_create_admin_and_audit_verify(capsys: pytest.CaptureFixture[str]) -> None:
    username = f"cli.{os.urandom(3).hex()}"
    assert cli.main(["create-admin", "--username", username, "--full-name", "Администратор"]) == 0
    out = capsys.readouterr().out
    assert username in out and "Vaqtinchalik parol:" in out
    assert cli.main(["create-admin", "--username", username, "--full-name", "X"]) == 1
    assert cli.main(["audit-verify"]) == 0
    assert cli.main(["cleanup"]) == 0


def test_cli_rewrap_roundtrip(tmp_path: Path) -> None:
    from app.core.config import get_settings

    new_kek = os.urandom(32)
    path = tmp_path / "kek"
    path.write_text(base64.b64encode(new_kek).decode())
    assert cli.main(["rewrap-keys", "--new-kek-file", str(path)]) == 0
    with get_engine("migrator").begin() as conn:
        keystore.rewrap_all(conn, new_kek, get_settings().key_bytes("master_kek"))
    keystore.invalidate_keyring()
    assert keystore.decrypt(Purpose.PII, keystore.encrypt(Purpose.PII, b"x", "a"), "a") == b"x"
