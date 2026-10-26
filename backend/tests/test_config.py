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


def test_smtp_host_without_recipients_is_a_problem() -> None:
    assert any("smtp_to" in p for p in make(smtp_host="relay").problems())
    assert make(smtp_host="relay", smtp_to="a@uge.uz").problems() == []


def test_etl_engine_has_long_statement_timeout() -> None:
    from sqlalchemy import text

    from app.core.db import get_engine

    with get_engine("etl").connect() as conn:
        assert conn.execute(text("SHOW statement_timeout")).scalar_one() == "30min"


def test_smtp_password_without_tls_is_a_problem() -> None:
    plain = make(smtp_password="x", smtp_starttls=False, smtp_ssl=False)
    assert any("starttls" in p or "ssl" in p for p in plain.problems())
    assert make(smtp_password="x", smtp_starttls=True, smtp_ssl=False).problems() == []
    assert make(smtp_password="x", smtp_starttls=False, smtp_ssl=True).problems() == []
    assert make(smtp_password="", smtp_starttls=False, smtp_ssl=False).problems() == []


def test_smtp_to_with_header_injection_is_a_problem_and_is_dropped() -> None:
    s = make(smtp_to="a@b.uz\r\nBcc: x@y")
    assert s.smtp_recipients == []
    assert any("smtp_to" in p for p in s.problems())


def test_smtp_to_with_valid_addresses_has_no_problems() -> None:
    assert make(smtp_to="a@uge.uz, b@uge.uz").problems() == []


def test_env_defaults_to_prod_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENV", raising=False)
    assert Settings().env == "prod"
