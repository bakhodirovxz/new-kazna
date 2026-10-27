import smtplib
import ssl
from collections.abc import Callable, Iterator
from dataclasses import replace
from email.message import EmailMessage
from typing import Any, ClassVar

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core import integrations
from app.core.db import get_engine
from app.etl import probes
from app.etl.notify import (
    LiveEmailNotifier,
    Notification,
    SmtpConfig,
    smtp_config,
    smtp_probe,
)

CFG = SmtpConfig(host="relay.uge.uz", port=587, sender="ugk@uge.uz",
                 recipients=["kazna@uge.uz"], username="ugk", password="pw", starttls=True,
                 ssl=False)
NOTE = Notification("etl_failed", "Загрузка завершилась ошибкой", "Шаг: facts")


class FakeSMTP:
    fail: ClassVar[BaseException | None] = None
    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(self, host: str, port: int, timeout: float, context: Any = None) -> None:
        if FakeSMTP.fail is not None:
            raise FakeSMTP.fail
        self.host, self.port = host, port
        self.tls = False
        self.login_args: tuple[str, str] | None = None
        self.sent: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self, context: Any = None) -> None:
        self.tls = True

    def login(self, user: str, password: str) -> None:
        self.login_args = (user, password)

    def noop(self) -> tuple[int, bytes]:
        return 250, b"ok"

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    FakeSMTP.fail = None
    FakeSMTP.instances.clear()
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.integration_credentials"))
        conn.execute(text("DELETE FROM core.integration_checks"))


def test_live_notifier_uses_current_config() -> None:
    LiveEmailNotifier(loader=lambda: CFG, smtp_factory=FakeSMTP).notify(NOTE)
    smtp = FakeSMTP.instances[-1]
    assert (smtp.host, smtp.tls, smtp.login_args) == ("relay.uge.uz", True, ("ugk", "pw"))
    assert smtp.sent[0]["To"] == "kazna@uge.uz"
    LiveEmailNotifier(loader=lambda: None, smtp_factory=FakeSMTP).notify(NOTE)
    assert len(FakeSMTP.instances) == 1


def test_smtp_config_reads_panel_and_secret(setting: Callable[[str, object], None]) -> None:
    assert smtp_config() is None
    setting("smtp.host", "relay.uge.uz")
    assert smtp_config() is None  # qabul qiluvchi yo'q
    setting("notify.email_to", ["kazna@uge.uz"])
    setting("smtp.port", 587)
    with get_engine("app").begin() as conn:
        integrations.store_secret(conn, "smtp.password", "Panel-Secret-1", None)
    cfg = smtp_config()
    assert cfg is not None
    assert (cfg.host, cfg.port, cfg.recipients, cfg.password) == (
        "relay.uge.uz", 587, ["kazna@uge.uz"], "Panel-Secret-1")


@pytest.mark.parametrize(("fail", "code"), [
    (None, "ok"),
    (smtplib.SMTPAuthenticationError(535, b"bad"), "auth_failed"),
    (ssl.SSLError("bad cert"), "tls_failed"),
    (TimeoutError(), "timeout"),
    (smtplib.SMTPServerDisconnected("gone"), "protocol_error"),
    (ConnectionRefusedError(), "connect_failed"),
])
def test_probe_maps_failures_to_safe_codes(fail: BaseException | None, code: str) -> None:
    FakeSMTP.fail = fail
    assert smtp_probe(loader=lambda: CFG, smtp_factory=FakeSMTP) == code


def test_probe_refuses_unconfigured_and_plaintext_auth() -> None:
    assert smtp_probe(loader=lambda: None, smtp_factory=FakeSMTP) == "not_configured"
    plain = replace(CFG, starttls=False)
    assert smtp_probe(loader=lambda: plain, smtp_factory=FakeSMTP) == "insecure_refused"
    assert FakeSMTP.instances == []


def _enqueue(status: str = "pending", age: str = "0 minutes") -> int:
    with get_engine("app").begin() as conn:
        return int(conn.execute(text(
            "INSERT INTO core.integration_checks (name, requested_by, status, requested_at) "
            "VALUES ('smtp', 1, :s, now() - CAST(:a AS interval)) RETURNING id"),
            {"s": status, "a": age}).scalar_one())


def _check(row_id: int) -> Any:
    with get_engine("app").connect() as conn:
        return conn.execute(text("SELECT status, code, finished_at FROM core.integration_checks "
                                 "WHERE id = :i"), {"i": row_id}).one()


def test_process_checks_runs_probe_and_expires_stuck(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probes, "PROBES", {"smtp": lambda: "auth_failed"})
    stuck = _enqueue("running", "10 minutes")
    fresh = _enqueue()
    assert probes.process_integration_checks() == 1
    assert tuple(_check(fresh))[:2] == ("failed", "auth_failed")
    assert _check(fresh).finished_at is not None
    assert tuple(_check(stuck))[:2] == ("failed", "timeout")


def test_probe_exception_text_is_not_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> str:
        raise RuntimeError("login failed for password=Panel-Secret-1")

    monkeypatch.setattr(probes, "PROBES", {"smtp": boom})
    row_id = _enqueue()
    assert probes.process_integration_checks() == 1
    assert tuple(_check(row_id))[:2] == ("failed", "error")


def test_smtp_config_falls_back_to_env_when_db_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """A04b.R2: DB ishlamasa ham (ops-check "DB unreachable", ETL xatosi) xat env orqali ketadi."""
    from pydantic import SecretStr

    from app.core.config import Settings
    from app.etl import notify

    class _Down:
        def connect(self) -> Any:
            raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(notify, "get_engine", lambda role="app": _Down())
    monkeypatch.setattr(notify, "get_settings", lambda: Settings(
        smtp_host="relay.uge.uz", smtp_to="ops@uge.uz", smtp_password=SecretStr("env-pw")))
    cfg = smtp_config()
    assert cfg is not None
    assert (cfg.host, cfg.recipients, cfg.password) == ("relay.uge.uz", ["ops@uge.uz"], "env-pw")
    assert "env-pw" not in repr(cfg)
    monkeypatch.setattr(notify, "get_settings", lambda: Settings())
    assert smtp_config() is None


def test_probe_has_an_overall_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    from app.etl import notify

    class Slow(FakeSMTP):
        def noop(self) -> tuple[int, bytes]:
            time.sleep(2)
            return 250, b"ok"

    monkeypatch.setattr(notify, "SMTP_DEADLINE", 0.2)
    assert smtp_probe(loader=lambda: CFG, smtp_factory=Slow) == "timeout"
