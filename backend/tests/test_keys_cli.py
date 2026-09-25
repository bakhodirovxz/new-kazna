import base64
import os
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import cli
from app.auth.models import User
from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose, blind_index, blob_version
from app.core.db import get_engine, new_session
from app.core.errors import register_error_handlers
from app.core.reencrypt import retire_unused, versions_in_use
from app.etl.db import etl_transaction
from app.main import _mount_openapi, create_app
from tests.helpers import SeedUser, issue_session, login, use_session


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


def test_rotate_failure_rolls_back_and_audits_fail(
    make_user: Callable[..., SeedUser], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling (fix round 1): mutatsiya+commit avval, audit "ok" keyin; xatoda rollback +
    audit "fail". Bu yerda `reencrypt`ni yiqitib, ikkalasini ham isbotlaymiz.

    `raise_server_exceptions=False` — aks holda Starlette'ning `TestClient`i (standart
    `raise_server_exceptions=True`) 500 javobini olib berish o'rniga asl istisnoni testning
    o'ziga qayta ko'taradi (`test_errors_middleware.py`dagi mavjud pattern bilan bir xil)."""
    import app.admin.keys_router as router_mod

    def _boom(*_a: object, **_k: object) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(router_mod, "reencrypt", _boom)
    with get_engine("app").begin() as conn:
        before = conn.execute(
            text("SELECT count(*) FROM core.crypto_keys WHERE purpose='mfa'")
        ).scalar_one()

    with TestClient(
        create_app(), base_url="https://testserver", raise_server_exceptions=False
    ) as client:
        login(client, make_user("admin"))
        r = client.post("/api/v1/admin/keys/mfa/rotate")
    assert r.status_code == 500

    with get_engine("app").begin() as conn:
        after = conn.execute(
            text("SELECT count(*) FROM core.crypto_keys WHERE purpose='mfa'")
        ).scalar_one()
        row = conn.execute(
            text(
                "SELECT result, details FROM core.audit_log WHERE action='admin.key.rotated' "
                "ORDER BY id DESC LIMIT 1"
            )
        ).mappings().first()
    assert after == before, "rotate rollback qilinmadi — yangi versiya baribir yozildi"
    assert row is not None
    assert row["result"] == "fail"
    assert row["details"]["error"] == "RuntimeError"


def test_api_rotate_leaves_dwh_columns_on_old_version_and_retire_keeps_it(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """Fix r1 (I1): `POST /admin/keys/{purpose}/rotate` `ugk_app` ulanishida ishlaydi va
    endi faqat `role="app"` (`core.*`) ustunlarni qayta shifrlaydi —
    `dwh.dim_counterparty.inn_enc` (`role="migrator"`) ustuni ESKI versiyada qoladi.
    `retire_unused` shu sabab o'sha eski versiyani "hali ishlatilyapti" deb saqlab qoladi:
    `versions_in_use` BARCHA rollardagi (app VA migrator) ustunlarni skanerlaydi. dwh
    ustunini qayta shifrlash faqat operator `rotate-key` CLI buyrug'i (migrator ulanishi)
    orqali bajariladi — `test_dwh_dims.py::test_counterparty_inn_reencrypted_on_pii_rotation`
    aynan shuni tekshiradi."""
    code = f"CP-K{uuid.uuid4().hex[:8]}"
    aad = f"dwh.dim_counterparty.inn_enc:{code}"
    bidx = blind_index(get_settings().key_bytes("blind_index_key"), "inn", "305222222")
    with etl_transaction() as conn:
        before_version = conn.execute(
            text("SELECT version FROM core.crypto_keys WHERE purpose='pii' AND status='active'")
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO dwh.dim_counterparty (code, name, kind, inn_enc, inn_bidx, "
                "src_system) VALUES (:c, 'ООО «К»', 'supplier', :e, :b, 'test')"
            ),
            {"c": code, "e": keystore.encrypt_str(Purpose.PII, "305222222", aad), "b": bidx},
        )
    try:
        login(client, make_user("admin"))
        r = client.post("/api/v1/admin/keys/pii/rotate")
        assert r.status_code == 200, r.text
        keystore.invalidate_keyring()
        with etl_transaction() as conn:
            blob = conn.execute(
                text("SELECT inn_enc FROM dwh.dim_counterparty WHERE code = :c"), {"c": code}
            ).scalar_one()
        assert blob_version(bytes(blob)) == before_version, (
            "API rotate role='app' — dwh ustuniga tegmasligi kerak edi"
        )
        with get_engine("migrator").begin() as conn:
            retired = retire_unused(conn, Purpose.PII, grace=timedelta(0), allow_short_grace=True)
        assert before_version not in retired, (
            "dwh ustuni hali eski versiyani ishlatyapti — retire uni saqlab qolishi kerak edi"
        )
    finally:
        with etl_transaction() as conn:
            conn.execute(text("DELETE FROM dwh.dim_counterparty WHERE code = :c"), {"c": code})


def test_retire_unused_respects_grace() -> None:
    kek = get_settings().key_bytes("master_kek")
    with get_engine("app").begin() as conn:
        keystore.rotate(conn, kek, Purpose.MFA)  # yangi active — "yangi" bo'lgani uchun
    keystore.invalidate_keyring()
    with get_engine("migrator").begin() as conn:
        assert retire_unused(conn, Purpose.MFA, grace=timedelta(hours=1)) == []
    keystore.invalidate_keyring()


def test_retire_unused_requires_min_grace_by_default() -> None:
    with get_engine("migrator").begin() as conn, pytest.raises(ValueError, match="10"):
        retire_unused(conn, Purpose.MFA, grace=timedelta(minutes=1))


def test_retire_unused_allow_short_grace_bypasses_minimum() -> None:
    with get_engine("migrator").begin() as conn:
        # Faqat ValueError ko'tarilmasligini tekshiramiz; natija bo'sh bo'lishi ham mumkin
        # (masalan, active kalit hozirgina yaratilgan bo'lsa — "fresh" tekshiruvi ishlaydi).
        retire_unused(conn, Purpose.MFA, grace=timedelta(0), allow_short_grace=True)


def test_retire_unused_refuses_purpose_without_registry_columns() -> None:
    """I1: INTEGRATION hali REGISTRY qilinmagan (BANK Task 2'da dwh.dim_bank.account_enc
    bilan ro'yxatga olindi) — retire uni yo'q qilishi mumkin emas, aks holda o'sha
    maqsaddagi ustunlar kelajakda REGISTRY qilinganda allaqachon o'qib bo'lmaydigan holga
    kelgan bo'lardi."""
    with get_engine("migrator").begin() as conn:
        before = conn.execute(
            text(
                "SELECT version, status FROM core.crypto_keys WHERE purpose = ANY(:ps) "
                "ORDER BY purpose, version"
            ),
            {"ps": [Purpose.INTEGRATION.value]},
        ).all()
        for purpose in (Purpose.INTEGRATION,):
            assert retire_unused(conn, purpose, grace=timedelta(0), allow_short_grace=True) == []
        after = conn.execute(
            text(
                "SELECT version, status FROM core.crypto_keys WHERE purpose = ANY(:ps) "
                "ORDER BY purpose, version"
            ),
            {"ps": [Purpose.INTEGRATION.value]},
        ).all()
    assert before == after, "REGISTRY'siz maqsad uchun crypto_keys o'zgarmasligi kerak"


def test_retire_unused_invariant_independent_of_order(
    make_user: Callable[..., SeedUser],
) -> None:
    """I2: kept/retired to'plamlarni testning O'ZI qurgan (yangi rotatsiya qilingan)
    versiyalar asosida isbotlaydi — boshqa testlar oldindan qoldirgan crypto_keys
    holatiga (ya'ni testlar bajarilish tartibiga) bog'liq emas."""
    kek = get_settings().key_bytes("master_kek")

    def _rotate_mfa() -> int:
        with get_engine("app").begin() as conn:
            v = keystore.rotate(conn, kek, Purpose.MFA)
        keystore.invalidate_keyring()
        return v

    v_unused = _rotate_mfa()  # hech qanday qator hech qachon shu versiyaga yozilmaydi
    v_kept = _rotate_mfa()  # v_unused -> decrypt_only; v_kept endi active
    user = make_user("admin")  # totp_secret_enc joriy active (v_kept) bilan shifrlanadi
    v_active = _rotate_mfa()  # v_kept -> decrypt_only (hali user tomonidan ishlatiladi)

    with new_session() as s:
        blob = s.execute(select(User.totp_secret_enc).where(User.id == user.id)).scalar_one()
    assert blob_version(bytes(blob)) == v_kept

    with get_engine("migrator").begin() as conn:
        statuses = dict(
            conn.execute(
                text(
                    "SELECT version, status FROM core.crypto_keys "
                    "WHERE purpose='mfa' AND version = ANY(:vs)"
                ),
                {"vs": [v_unused, v_kept, v_active]},
            ).all()
        )
        assert statuses == {v_unused: "decrypt_only", v_kept: "decrypt_only", v_active: "active"}

        in_use = versions_in_use(conn, Purpose.MFA)
        assert v_kept in in_use
        assert v_unused not in in_use

        retired = retire_unused(conn, Purpose.MFA, grace=timedelta(0), allow_short_grace=True)
        assert v_unused in retired
        assert v_kept not in retired
        assert v_active not in retired

        rows = {
            row["version"]: row
            for row in conn.execute(
                text(
                    "SELECT version, status, wrapped_key FROM core.crypto_keys "
                    "WHERE purpose='mfa' AND version = ANY(:vs)"
                ),
                {"vs": [v_unused, v_kept]},
            ).mappings()
        }
    assert rows[v_unused]["status"] == "retired"
    assert bytes(rows[v_unused]["wrapped_key"]) == b""
    assert rows[v_kept]["status"] == "decrypt_only"
    assert bytes(rows[v_kept]["wrapped_key"]) != b""

    # Kept versiya hamon ochiladi (retire uni buzmadi):
    keystore.invalidate_keyring()
    with new_session() as s:
        blob2 = s.execute(select(User.totp_secret_enc).where(User.id == user.id)).scalar_one()
    assert (
        keystore.decrypt_str(Purpose.MFA, bytes(blob2), f"core.users.totp_secret_enc:{user.id}")
        == user.totp_secret
    )


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


def test_mount_openapi_prod_branch_requires_admin_settings(
    make_user: Callable[..., SeedUser],
) -> None:
    """I3: prod branch (`_mount_openapi(app, protected=True)`)ni to'g'ridan-to'g'ri, alohida
    "yalang'och" FastAPI ilovasida sinaymiz — `create_app()`'ning `lifespan`i
    `settings.env="prod"`ni test kalitlari (`TEST_KEYS`) bilan bloklab qo'yar edi."""
    probe_app = FastAPI()
    register_error_handlers(probe_app)
    _mount_openapi(probe_app, protected=True)

    with TestClient(probe_app, base_url="https://testserver") as probe:
        r = probe.get("/api/v1/openapi.json")
        assert r.status_code == 401, r.text

        limited = make_user("vnutr_kontrol")
        token, csrf, _sid = issue_session(limited.id)
        use_session(probe, token, csrf)
        r = probe.get("/api/v1/openapi.json")
        assert r.status_code == 403, r.text

        admin = make_user("admin")
        token, csrf, _sid = issue_session(admin.id)
        use_session(probe, token, csrf)
        r = probe.get("/api/v1/openapi.json")
        assert r.status_code == 200, r.text


def test_cli_create_admin_and_audit_verify(capsys: pytest.CaptureFixture[str]) -> None:
    username = f"cli.{os.urandom(3).hex()}"
    assert cli.main(["create-admin", "--username", username, "--full-name", "Администратор"]) == 0
    out = capsys.readouterr().out
    assert username in out and "Vaqtinchalik parol:" in out
    assert cli.main(["create-admin", "--username", username, "--full-name", "X"]) == 1
    with get_engine("app").begin() as conn:
        row = conn.execute(
            text(
                "SELECT object_type, object_id FROM core.audit_log "
                "WHERE action='admin.user.created' ORDER BY id DESC LIMIT 1"
            )
        ).mappings().first()
    assert row is not None
    assert row["object_type"] == "user"
    assert row["object_id"] is not None and row["object_id"].isdigit()
    assert cli.main(["audit-verify"]) == 0
    assert cli.main(["cleanup"]) == 0


def test_cli_retire_keys_grace_minutes_minimum() -> None:
    with pytest.raises(SystemExit):
        cli.main(["retire-keys", "--grace-minutes", "5"])


def test_cli_retire_failure_audits_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: object, **_k: object) -> list[int]:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "retire_unused", _boom)
    with pytest.raises(RuntimeError):
        cli.main(["retire-keys", "--grace-minutes", "10"])
    with get_engine("app").begin() as conn:
        row = conn.execute(
            text(
                "SELECT result, details FROM core.audit_log WHERE action='admin.key.retired' "
                "ORDER BY id DESC LIMIT 1"
            )
        ).mappings().first()
    assert row is not None
    assert row["result"] == "fail"
    assert row["details"]["error"] == "RuntimeError"


def test_cli_rewrap_refuses_same_kek(tmp_path: Path) -> None:
    current = get_settings().key_bytes("master_kek")
    path = tmp_path / "same_kek"
    path.write_text(base64.b64encode(current).decode())
    assert cli.main(["rewrap-keys", "--new-kek-file", str(path)]) == 1


def test_cli_rewrap_failure_audits_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    new_kek = os.urandom(32)
    path = tmp_path / "kek_fail"
    path.write_text(base64.b64encode(new_kek).decode())

    def _boom(*_a: object, **_k: object) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(keystore, "rewrap_all", _boom)
    with pytest.raises(RuntimeError):
        cli.main(["rewrap-keys", "--new-kek-file", str(path)])
    with get_engine("app").begin() as conn:
        row = conn.execute(
            text(
                "SELECT result, details FROM core.audit_log WHERE action='admin.key.rewrapped' "
                "ORDER BY id DESC LIMIT 1"
            )
        ).mappings().first()
    assert row is not None
    assert row["result"] == "fail"
    assert row["details"]["error"] == "RuntimeError"


def test_cli_rewrap_roundtrip(tmp_path: Path) -> None:
    new_kek = os.urandom(32)
    path = tmp_path / "kek"
    path.write_text(base64.b64encode(new_kek).decode())
    assert cli.main(["rewrap-keys", "--new-kek-file", str(path)]) == 0
    with get_engine("migrator").begin() as conn:
        keystore.rewrap_all(conn, new_kek, get_settings().key_bytes("master_kek"))
    keystore.invalidate_keyring()
    assert keystore.decrypt(Purpose.PII, keystore.encrypt(Purpose.PII, b"x", "a"), "a") == b"x"
