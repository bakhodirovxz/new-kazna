import base64
import json
from collections.abc import Callable, Iterator
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app.core import integrations
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.etl.onec.client import (
    OneCClient,
    OneCConfig,
    OneCError,
    OneCFormatError,
    parse_json,
    verify_setting,
)
from app.etl.types import ConnectorUnavailableError
from tests.helpers import clear_setting, put_setting

BASE = "https://1c.test/con2026/hs/aiassistant"


def _cfg(base: str = BASE, user: str = "api-user",
         password: str = "s3cr3t-pass", *,  # noqa: S107
         max_bytes: int = 64 * 1024 * 1024, allow_http: bool = False) -> OneCConfig:
    return OneCConfig(base, user, password, max_bytes, "", allow_http)


def _client(handler: Callable[[httpx.Request], httpx.Response], **kw: object) -> OneCClient:
    cfg = _cfg(**kw)  # type: ignore[arg-type]
    return OneCClient(cfg, transport=httpx.MockTransport(handler))


def test_config_validation() -> None:
    with pytest.raises(ConfigError, match="https"):
        OneCClient(_cfg("http://10.0.90.52/con2026/hs/aiassistant"))
    insecure = OneCClient(_cfg("http://10.0.90.52/x", allow_http=True))
    assert insecure.insecure is True
    with pytest.raises(ConfigError):
        OneCClient(_cfg(user=""))
    with pytest.raises(ConfigError):
        OneCClient(_cfg(password=""))
    with pytest.raises(ConfigError):
        OneCClient(_cfg("ftp://1c.test/x"))
    secure = OneCClient(_cfg())
    assert secure.insecure is False and secure.http.trust_env is False


def test_post_sends_json_with_basic_auth() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"\xef\xbb\xbf" + b'{"items": [{"sum": 1.10}]}')

    data = _client(handler).post("/budget", {"Year": 2026, "Mode": "plan"})
    assert data == {"items": [{"sum": Decimal("1.10")}]}
    request = seen[0]
    assert str(request.url) == f"{BASE}/budget" and request.method == "POST"
    assert json.loads(request.content) == {"Year": 2026, "Mode": "plan"}
    expected = base64.b64encode(b"api-user:s3cr3t-pass").decode()
    assert request.headers["authorization"] == f"Basic {expected}"


def test_html_error_page_is_format_error() -> None:
    client = _client(lambda r: httpx.Response(200, text="<html><body>Ошибка 1С</body></html>",
                                              headers={"content-type": "text/html"}))
    with pytest.raises(OneCFormatError, match="не JSON") as exc:
        client.post("/payments", {})
    assert not isinstance(exc.value, ConnectorUnavailableError)


def test_empty_and_non_utf8_bodies() -> None:
    with pytest.raises(OneCFormatError, match="пустой"):
        _client(lambda r: httpx.Response(200, content=b"\xef\xbb\xbf  ")).post("/x", {})
    with pytest.raises(OneCFormatError):
        _client(lambda r: httpx.Response(200, content=b"\xff\xfe{}")).post("/x", {})


def test_server_errors_and_timeouts_are_retryable() -> None:
    with pytest.raises(ConnectorUnavailableError, match="503"):
        _client(lambda r: httpx.Response(503)).post("/payments", {})

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ConnectorUnavailableError, match="тайм-аут"):
        _client(timeout).post("/payments", {})

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ConnectorUnavailableError):
        _client(refused).post("/payments", {})


def test_auth_failure_and_redirect_are_not_retryable() -> None:
    with pytest.raises(OneCError, match="доступ") as exc:
        _client(lambda r: httpx.Response(401)).post("/payments", {})
    assert "s3cr3t" not in str(exc.value)
    with pytest.raises(OneCError, match="302"):
        _client(lambda r: httpx.Response(302, headers={"location": "https://evil.test/"})).post(
            "/payments", {})


def test_response_size_cap() -> None:
    client = _client(lambda r: httpx.Response(200, content=b'{"a": "' + b"x" * 500 + b'"}'),
                     max_bytes=100)
    with pytest.raises(OneCFormatError, match="больше"):
        client.post("/payments", {})


def test_parse_json_keeps_decimals() -> None:
    assert parse_json(b'{"sum": 2500000.50}', "/p") == {"sum": Decimal("2500000.50")}


def test_verify_setting(tmp_path: Path) -> None:
    assert verify_setting(str(tmp_path / "missing.pem")) is True
    empty = tmp_path / "empty.pem"
    empty.write_text("", encoding="ascii")
    assert verify_setting(str(empty)) is True
    bad = tmp_path / "bad.pem"
    bad.write_text("-----BEGIN CERTIFICATE-----\nnope\n-----END CERTIFICATE-----\n",
                   encoding="ascii")
    with pytest.raises(ConfigError):
        verify_setting(str(bad))


@pytest.fixture
def onec_panel() -> Iterator[None]:
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.integration_credentials WHERE name LIKE 'onec.%'"))
    for key in ("onec.base_url", "onec.max_mb"):
        clear_setting(key)


@pytest.mark.usefixtures("onec_panel")
def test_config_load_from_panel_and_configured() -> None:
    with get_engine("app").connect() as conn:
        assert integrations.configured(conn, "onec") is False
        with pytest.raises(ConfigError, match="1С"):
            OneCConfig.load(conn)
    put_setting("onec.base_url", BASE)
    put_setting("onec.max_mb", 8)
    with get_engine("app").begin() as conn:
        assert integrations.configured(conn, "onec") is False  # sirlar yo'q
        integrations.store_secret(conn, "onec.username", "api-user", None)
        integrations.store_secret(conn, "onec.password", "s3cr3t-pass", None)
    with get_engine("app").connect() as conn:
        assert integrations.configured(conn, "onec") is True
        cfg = OneCConfig.load(conn)
    assert (cfg.base_url, cfg.username, cfg.password, cfg.max_bytes) == (
        BASE, "api-user", "s3cr3t-pass", 8 * 1024 * 1024)
    assert cfg.allow_http == get_settings().onec_allow_http
    assert "s3cr3t" not in repr(cfg)


@pytest.mark.usefixtures("onec_panel")
def test_http_rule_blocks_plain_http_unless_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    put_setting("onec.base_url", "http://10.0.90.52/con2026/hs/aiassistant")
    rule = integrations.RULES["onec"]
    with get_engine("app").connect() as conn:
        assert rule(conn) == ("insecure_http", "onec.base_url")
    monkeypatch.setattr(integrations, "get_settings",
                        lambda: get_settings().model_copy(update={"onec_allow_http": True}))
    with get_engine("app").connect() as conn:
        assert rule(conn) is None
