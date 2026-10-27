import json
import logging
from collections.abc import Callable

import httpx
import pytest

from app.core import integrations
from app.core.config import ConfigError
from app.core.db import get_engine
from app.etl.notify import CompositeNotifier, Notification, build_notifier
from app.etl.telegram import (
    MAX_TEXT,
    TelegramClient,
    TelegramConfig,
    TelegramError,
    TelegramNotifier,
    telegram_config,
    telegram_probe,
)

TOKEN = "123456789:" + "A" * 35


def _client(handler: Callable[[httpx.Request], httpx.Response],
            sleeps: list[float] | None = None) -> TelegramClient:
    return TelegramClient(TOKEN, transport=httpx.MockTransport(handler),
                          sleep=(sleeps if sleeps is not None else []).append)


def test_send_posts_plain_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    _client(handler).send(42, "Привет" + "x" * 5000)
    request = seen[0]
    assert request.url.path == f"/bot{TOKEN}/sendMessage" and request.method == "POST"
    body = json.loads(request.content)
    assert body["chat_id"] == 42 and body["disable_web_page_preview"] is True
    assert len(body["text"]) == MAX_TEXT and body["text"].startswith("Привет")
    assert "parse_mode" not in body


def test_429_waits_retry_after_once() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"ok": False, "error_code": 429,
                                             "parameters": {"retry_after": 3}})
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    _client(handler, sleeps).send(1, "t")
    assert sleeps == [3.0] and len(calls) == 2
    always = _client(lambda r: httpx.Response(429, json={"parameters": {"retry_after": 999}}),
                     sleeps)
    with pytest.raises(TelegramError, match="429"):
        always.send(1, "t")
    assert sleeps[-1] == 30.0


def test_server_error_retried_once_then_fails() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(502)

    with pytest.raises(TelegramError, match="502"):
        _client(handler).send(1, "t")
    assert len(calls) == 2
    with pytest.raises(TelegramError, match="403"):
        _client(lambda r: httpx.Response(403, json={"ok": False})).send(1, "t")


def test_token_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot connect to {request.url}", request=request)

    with pytest.raises(TelegramError) as exc:
        _client(refused).send(1, "t")
    _client(lambda r: httpx.Response(200, json={"ok": True})).send(1, "t")
    assert TOKEN not in str(exc.value) and TOKEN not in repr(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
    assert TOKEN not in caplog.text
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_invalid_token_is_config_error() -> None:
    with pytest.raises(ConfigError) as exc:
        TelegramClient("12345:short")
    assert "12345:short" not in str(exc.value)
    assert TelegramClient(TOKEN, proxy="http://10.0.0.1:3128").http.trust_env is False


def test_notifier_sends_to_all_chats_and_survives_failure() -> None:
    chats: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        chat = json.loads(request.content)["chat_id"]
        chats.append(chat)
        return httpx.Response(400 if chat == 1 else 200, json={"ok": chat != 1})

    notifier = TelegramNotifier(lambda: TelegramConfig(TOKEN, [1, 2], True),
                                lambda cfg: _client(handler))
    notifier.notify(Notification("etl_failed", "Загрузка «onec» завершилась ошибкой", "тело"))
    assert chats == [1, 2]


def test_notifier_without_config_is_silent() -> None:
    called: list[int] = []
    TelegramNotifier(lambda: None, lambda cfg: called.append(1)).notify(  # type: ignore[arg-type,return-value]
        Notification("etl_failed", "s", "b"))
    assert called == []


def test_config_comes_from_panel_secret_and_setting(setting: Callable[[str, object], None]) -> None:
    assert telegram_config() is None
    setting("telegram.chat_ids", ["-100500", "7"])
    assert telegram_config() is None  # token yo'q
    with get_engine("app").begin() as conn:
        integrations.store_secret(conn, "telegram.bot_token", TOKEN, None)
    try:
        assert telegram_config() == TelegramConfig(TOKEN, [-100500, 7], False, "off")
    finally:
        with get_engine("app").begin() as conn:
            integrations.clear_secret(conn, "telegram.bot_token")


def test_build_notifier_includes_telegram() -> None:
    notifier = build_notifier()
    assert isinstance(notifier, CompositeNotifier)
    assert any(isinstance(n, TelegramNotifier) for n in notifier.notifiers)


def test_probe_codes() -> None:
    assert telegram_probe(lambda: None) == "not_configured"
    cfg = TelegramConfig(TOKEN, [1])

    def factory(
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> Callable[..., TelegramClient]:
        return lambda c: _client(handler)

    ok = factory(lambda r: httpx.Response(200, json={"ok": True}))
    assert telegram_probe(lambda: cfg, ok) == "ok"
    assert telegram_probe(lambda: cfg, factory(lambda r: httpx.Response(401))) == "auth_failed"
    assert telegram_probe(lambda: cfg, factory(lambda r: httpx.Response(500))) == "http_error"

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("x", request=request)

    assert telegram_probe(lambda: cfg, factory(refuse)) == "connect_failed"


def test_forward_alerts_is_opt_in_and_title_only() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content)["text"])
        return httpx.Response(200, json={"ok": True})

    note = Notification("etl_failed", "Загрузка «banks» завершилась ошибкой",
                        "Филиал ГЭС-1: 1 234 567 000 сум")
    TelegramNotifier(lambda: TelegramConfig(TOKEN, [1], False), lambda cfg: _client(handler)
                     ).notify(note)
    assert sent == []  # sukut bo'yicha yuborilmaydi
    TelegramNotifier(lambda: TelegramConfig(TOKEN, [1], True), lambda cfg: _client(handler)
                     ).notify(note)
    assert sent == ["UGEKAZNA: Загрузка «banks» завершилась ошибкой"]  # tafsilotsiz
