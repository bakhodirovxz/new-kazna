import time

import pyotp

from app.auth import totp


def test_verify_accepts_current_and_blocks_replay() -> None:
    secret = totp.new_secret()
    now = time.time()
    code = pyotp.TOTP(secret).at(now)
    step = totp.verify(secret, code, None, now)
    assert step == int(now) // 30
    assert totp.verify(secret, code, step, now) is None


def test_verify_window_is_plus_minus_one_step() -> None:
    secret = totp.new_secret()
    now = time.time()
    current = int(now) // 30
    prev_code = pyotp.TOTP(secret).at((current - 1) * 30)
    far_code = pyotp.TOTP(secret).at((current + 2) * 30)
    assert totp.verify(secret, prev_code, None, now) == current - 1
    assert totp.verify(secret, far_code, None, now) is None


def test_verify_rejects_malformed() -> None:
    secret = totp.new_secret()
    for bad in ("", "12345", "1234567", "abcdef", "12 345"):
        assert totp.verify(secret, bad, None, time.time()) is None


def test_secret_is_160_bits() -> None:
    assert len(totp.new_secret()) == 32


def test_provisioning_uri_and_qr() -> None:
    uri = totp.provisioning_uri(totp.new_secret(), "ali.valiyev")
    assert uri.startswith("otpauth://totp/UGEKAZNA:ali.valiyev?")
    assert "issuer=UGEKAZNA" in uri
    assert totp.qr_data_uri(uri).startswith("data:image/svg+xml")


def test_backup_codes() -> None:
    codes = totp.generate_backup_codes()
    assert len(codes) == totp.BACKUP_CODE_COUNT == len(set(codes))
    for c in codes:
        assert len(c) == 14 and c[4] == "-" and c[9] == "-"
        normalized = totp.normalize_backup_code(c)
        assert normalized == c.replace("-", "")
        assert normalized is not None and len(normalized) == 12
        assert totp.normalize_backup_code(c.lower().replace("-", " ")) == c.replace("-", "")
    assert totp.normalize_backup_code("123456") is None
    assert totp.normalize_backup_code("ABCDE-FGH") is None
