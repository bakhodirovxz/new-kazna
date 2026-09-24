import base64

import pytest

from app.core.config import TEST_KEYS, ConfigError, Settings

GOOD_KEY = base64.b64encode(bytes(range(100, 132))).decode()


def make(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "master_kek": GOOD_KEY,
        "blind_index_key": GOOD_KEY,
        "session_pepper": GOOD_KEY,
        "db_app_password": "x",
        "redis_password": "y",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_key_bytes_decodes_32_bytes() -> None:
    assert make().key_bytes("master_kek") == bytes(range(100, 132))


def test_key_bytes_rejects_wrong_length() -> None:
    s = make(master_kek=base64.b64encode(b"short").decode())
    with pytest.raises(ConfigError, match="32 bayt"):
        s.key_bytes("master_kek")


def test_key_bytes_rejects_non_base64() -> None:
    with pytest.raises(ConfigError, match="base64"):
        make(master_kek="not base64 !!!").key_bytes("master_kek")


def test_no_problems_for_valid_test_settings() -> None:
    assert make(env="test").problems() == []


def test_prod_rejects_test_keys_http_and_fast_hash() -> None:
    test_key = sorted(TEST_KEYS)[0]
    s = make(env="prod", master_kek=test_key, base_url="http://x", argon2_profile="fast_test")
    joined = " | ".join(s.problems())
    assert "test kaliti" in joined
    assert "https" in joined
    assert "fast_test" in joined


def test_fast_hash_only_in_test_env() -> None:
    assert any("fast_test" in p for p in make(env="dev", argon2_profile="fast_test").problems())


def test_pg_url_escapes_password() -> None:
    url = make(db_app_password="p@ss:w/rd").pg_url("app")
    assert "p%40ss%3Aw%2Frd@" in url
    assert url.startswith("postgresql+psycopg://ugk_app:")
