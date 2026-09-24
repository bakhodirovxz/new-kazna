import os

import pytest

from app.core.crypto import (
    CryptoError,
    Keyring,
    Purpose,
    blind_index,
    blob_version,
    keyed_hash,
    new_dek,
    unwrap_key,
    wrap_key,
)


@pytest.fixture
def ring() -> Keyring:
    return Keyring(
        keys={(Purpose.PII, 1): os.urandom(32), (Purpose.PII, 2): os.urandom(32)},
        active={Purpose.PII: 2},
    )


def test_roundtrip_uses_active_version(ring: Keyring) -> None:
    blob = ring.encrypt(Purpose.PII, b"305123456", "core.t.c:1")
    assert blob[0] == 1
    assert blob_version(blob) == 2
    assert ring.decrypt(Purpose.PII, blob, "core.t.c:1") == b"305123456"


def test_same_plaintext_gives_different_ciphertexts(ring: Keyring) -> None:
    assert ring.encrypt(Purpose.PII, b"x", "a") != ring.encrypt(Purpose.PII, b"x", "a")


def test_wrong_aad_is_rejected(ring: Keyring) -> None:
    blob = ring.encrypt(Purpose.PII, b"secret", "core.t.c:1")
    with pytest.raises(CryptoError) as exc:
        ring.decrypt(Purpose.PII, blob, "core.t.c:2")
    assert exc.value.reason == "integrity"


def test_wrong_purpose_is_rejected(ring: Keyring) -> None:
    blob = ring.encrypt(Purpose.PII, b"secret", "a")
    other = Keyring(keys={(Purpose.BANK, 2): ring.keys[(Purpose.PII, 2)]}, active={})
    with pytest.raises(CryptoError):
        other.decrypt(Purpose.BANK, blob, "a")


def test_tampered_byte_is_rejected(ring: Keyring) -> None:
    blob = bytearray(ring.encrypt(Purpose.PII, b"secret", "a"))
    blob[-1] ^= 0x01
    with pytest.raises(CryptoError) as exc:
        ring.decrypt(Purpose.PII, bytes(blob), "a")
    assert exc.value.reason == "integrity"


def test_unknown_version_and_bad_format(ring: Keyring) -> None:
    blob = bytearray(ring.encrypt(Purpose.PII, b"s", "a"))
    blob[1:3] = (9).to_bytes(2, "big")
    with pytest.raises(CryptoError) as exc:
        ring.decrypt(Purpose.PII, bytes(blob), "a")
    assert exc.value.reason == "unknown_key_version"
    with pytest.raises(CryptoError) as exc2:
        ring.decrypt(Purpose.PII, b"\x02" + bytes(40), "a")
    assert exc2.value.reason == "bad_format"


def test_no_active_key() -> None:
    with pytest.raises(CryptoError) as exc:
        Keyring(keys={}, active={}).encrypt(Purpose.MFA, b"x", "a")
    assert exc.value.reason == "no_active_key"


def test_key_wrap_roundtrip_and_wrong_kek() -> None:
    kek, dek = os.urandom(32), new_dek()
    wrapped = wrap_key(kek, dek)
    assert unwrap_key(kek, wrapped) == dek
    with pytest.raises(CryptoError) as exc:
        unwrap_key(os.urandom(32), wrapped)
    assert exc.value.reason == "unwrap_failed"


def test_blind_index_normalizes_and_separates_purposes() -> None:
    key = os.urandom(32)
    assert blind_index(key, "inn", " 305 123 456 ") == blind_index(key, "inn", "305123456")
    assert blind_index(key, "inn", "ABC") == blind_index(key, "inn", "abc")
    assert blind_index(key, "inn", "1") != blind_index(key, "account", "1")
    assert len(blind_index(key, "inn", "1")) == 32


def test_keyed_hash_depends_on_label() -> None:
    key = os.urandom(32)
    assert keyed_hash(key, "session", "t") != keyed_hash(key, "mfa", "t")
