import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.bootstrap import bootstrap_runtime
from app.core import keystore
from app.core.config import Settings, get_settings
from app.core.crypto import CryptoError, Purpose, blob_version
from app.core.db import get_engine


def _kek() -> bytes:
    return get_settings().key_bytes("master_kek")


def test_ensure_keys_creates_one_active_key_per_purpose() -> None:
    with get_engine("app").begin() as conn:
        keystore.ensure_keys(conn, _kek())
        keystore.ensure_keys(conn, _kek())
        rows = conn.execute(
            text("SELECT purpose, count(*) FROM core.crypto_keys WHERE status='active' GROUP BY 1")
        ).all()
    assert {p for p, _ in rows} == {p.value for p in Purpose}
    assert all(n == 1 for _, n in rows)


def test_encrypt_decrypt_helpers() -> None:
    blob = keystore.encrypt_str(Purpose.PII, "10.0.0.1", "core.x.ip:1")
    assert keystore.decrypt_str(Purpose.PII, blob, "core.x.ip:1") == "10.0.0.1"


def test_rotate_keeps_old_versions_decryptable() -> None:
    old_blob = keystore.encrypt(Purpose.BANK, b"20208000900100001001", "core.b.a:1")
    with get_engine("app").begin() as conn:
        new_version = keystore.rotate(conn, _kek(), Purpose.BANK)
    keystore.invalidate_keyring()
    new_blob = keystore.encrypt(Purpose.BANK, b"x", "core.b.a:2")
    assert blob_version(new_blob) == new_version == blob_version(old_blob) + 1
    assert keystore.decrypt(Purpose.BANK, old_blob, "core.b.a:1") == b"20208000900100001001"


def test_decrypt_refreshes_stale_cache() -> None:
    stale = keystore.get_keyring()  # boshqa worker'dagi eski kesh
    with get_engine("app").begin() as conn:
        keystore.rotate(conn, _kek(), Purpose.INTEGRATION)
        fresh = keystore.load_keyring(conn, _kek())
    blob = fresh.encrypt(Purpose.INTEGRATION, b"1c-password", "core.i.p:1")
    assert keystore.get_keyring() is stale
    assert keystore.decrypt(Purpose.INTEGRATION, blob, "core.i.p:1") == b"1c-password"


def test_rewrap_all_with_new_kek_and_back() -> None:
    # rewrap_all operator amali — ugk_migrator (jadval egasi) sifatida bajariladi,
    # chunki ugk_app'ning wrapped_key ustunini yozish huquqi yo'q (I2 topilma).
    new_kek = os.urandom(32)
    blob = keystore.encrypt(Purpose.PII, b"v", "core.t.c:1")
    with get_engine("migrator").begin() as conn:
        count = keystore.rewrap_all(conn, _kek(), new_kek)
        assert count >= len(Purpose)
        ring = keystore.load_keyring(conn, new_kek)
        assert ring.decrypt(Purpose.PII, blob, "core.t.c:1") == b"v"
        keystore.rewrap_all(conn, new_kek, _kek())
    keystore.invalidate_keyring()
    assert keystore.decrypt(Purpose.PII, blob, "core.t.c:1") == b"v"


def test_pepper_is_32_bytes() -> None:
    assert len(keystore.pepper()) == 32


def test_etl_role_cannot_modify_keys() -> None:
    with get_engine("etl").begin() as conn, pytest.raises(ProgrammingError):
        conn.execute(text("UPDATE core.crypto_keys SET status = 'retired'"))


def test_etl_role_cannot_insert_keys() -> None:
    with (
        get_engine("etl").begin() as conn,
        pytest.raises(ProgrammingError, match="permission denied"),
    ):
        conn.execute(
            text(
                "INSERT INTO core.crypto_keys (purpose, version, wrapped_key, status) "
                "VALUES ('pii', 999, :w, 'active')"
            ),
            {"w": b"x" * 40},
        )


def test_app_role_cannot_rewrite_wrapped_key() -> None:
    with (
        get_engine("app").begin() as conn,
        pytest.raises(ProgrammingError, match="permission denied"),
    ):
        conn.execute(text("UPDATE core.crypto_keys SET wrapped_key = :w"), {"w": b"x" * 40})


def test_app_role_cannot_delete_keys() -> None:
    with (
        get_engine("app").begin() as conn,
        pytest.raises(ProgrammingError, match="permission denied"),
    ):
        conn.execute(text("DELETE FROM core.crypto_keys"))


def test_rotate_with_wrong_kek_raises_and_inserts_nothing() -> None:
    with get_engine("app").begin() as conn:
        before = conn.execute(
            text("SELECT count(*) FROM core.crypto_keys WHERE purpose = 'mfa'")
        ).scalar_one()
        with pytest.raises(CryptoError) as exc:
            keystore.rotate(conn, os.urandom(32), Purpose.MFA)
        assert exc.value.reason == "unwrap_failed"
        after = conn.execute(
            text("SELECT count(*) FROM core.crypto_keys WHERE purpose = 'mfa'")
        ).scalar_one()
    assert after == before


def test_ensure_keys_with_wrong_kek_raises_and_inserts_nothing() -> None:
    with get_engine("app").begin() as conn:
        before = conn.execute(text("SELECT count(*) FROM core.crypto_keys")).scalar_one()
        with pytest.raises(CryptoError) as exc:
            keystore.ensure_keys(conn, os.urandom(32))
        assert exc.value.reason == "unwrap_failed"
        after = conn.execute(text("SELECT count(*) FROM core.crypto_keys")).scalar_one()
    assert after == before


def test_bootstrap_with_wrong_kek_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    original = Settings.key_bytes

    def _wrong(self: Settings, name: str) -> bytes:
        if name == "master_kek":
            return os.urandom(32)
        return original(self, name)

    monkeypatch.setattr(Settings, "key_bytes", _wrong)
    with pytest.raises(CryptoError):
        bootstrap_runtime()
    keystore.invalidate_keyring()


def test_integrity_failure_does_not_refresh_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> None:
        raise AssertionError("integrity xatosida keyring keshi yangilanmasligi kerak")

    blob = bytearray(keystore.encrypt(Purpose.PII, b"x", "core.t.c:1"))
    blob[-1] ^= 0x01
    monkeypatch.setattr(keystore, "invalidate_keyring", _boom)
    with pytest.raises(CryptoError) as exc:
        keystore.decrypt(Purpose.PII, bytes(blob), "core.t.c:1")
    assert exc.value.reason == "integrity"
