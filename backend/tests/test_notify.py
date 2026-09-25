from email.message import EmailMessage
from typing import Any, ClassVar

import pytest

from app.core.config import get_settings
from app.etl.notify import (
    CompositeNotifier,
    EmailNotifier,
    LogNotifier,
    Notification,
    build_notifier,
)


class FakeSMTP:
    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(
        self, host: str, port: int, timeout: float, context: Any = None
    ) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.ssl_context = context
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

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)


def _email(**overrides: Any) -> EmailNotifier:
    params: dict[str, Any] = {
        "host": "relay.local", "port": 587, "sender": "ugk@uge.uz",
        "recipients": ["kazna@uge.uz", "it@uge.uz"], "password": "relay-secret",
        "smtp_factory": FakeSMTP,
    }
    params.update(overrides)
    return EmailNotifier(**params)


def test_email_is_sent_with_starttls_and_login() -> None:
    FakeSMTP.instances.clear()
    _email().notify(Notification("etl_failed", "Загрузка 1С завершилась ошибкой", "Шаг: facts"))
    smtp = FakeSMTP.instances[-1]
    assert (smtp.host, smtp.port) == ("relay.local", 587)
    assert smtp.tls is True
    assert smtp.login_args == ("ugk@uge.uz", "relay-secret")
    message = smtp.sent[0]
    assert message["Subject"] == "[UGEKAZNA] Загрузка 1С завершилась ошибкой"
    assert message["To"] == "kazna@uge.uz, it@uge.uz"
    assert "Шаг: facts" in message.get_content()


def test_subject_newlines_cannot_inject_headers() -> None:
    FakeSMTP.instances.clear()
    _email(password="").notify(Notification("etl_failed", "a\r\nBcc: evil@x.uz", "b"))
    smtp = FakeSMTP.instances[-1]
    assert smtp.login_args is None
    assert smtp.sent[0]["Bcc"] is None
    assert "\n" not in smtp.sent[0]["Subject"]


def test_smtp_failure_is_logged_not_raised() -> None:
    def broken(*_a: Any, **_k: Any) -> Any:
        raise ConnectionRefusedError("relay down")

    _email(smtp_factory=broken).notify(Notification("stale_data", "x", "y"))


def test_composite_continues_after_failing_notifier() -> None:
    received: list[str] = []

    class Boom:
        def notify(self, notification: Notification) -> None:
            raise RuntimeError("boom")

    class Collect:
        def notify(self, notification: Notification) -> None:
            received.append(notification.kind)

    CompositeNotifier([Boom(), Collect()]).notify(Notification("etl_quality", "s", "b"))
    assert received == ["etl_quality"]


def test_build_notifier_adds_email_only_when_configured() -> None:
    plain = build_notifier(get_settings().model_copy(update={"smtp_host": ""}))
    assert isinstance(plain, CompositeNotifier)
    assert [type(n) for n in plain.notifiers] == [LogNotifier]
    full = build_notifier(
        get_settings().model_copy(update={"smtp_host": "relay", "smtp_to": "a@uge.uz"})
    )
    assert isinstance(full, CompositeNotifier)
    assert [type(n) for n in full.notifiers] == [LogNotifier, EmailNotifier]


@pytest.mark.parametrize("raw", ["a@uge.uz, b@uge.uz", " a@uge.uz ,b@uge.uz,"])
def test_smtp_recipients_parsing(raw: str) -> None:
    settings = get_settings().model_copy(update={"smtp_to": raw})
    assert settings.smtp_recipients == ["a@uge.uz", "b@uge.uz"]


def test_login_refused_when_connection_is_not_encrypted() -> None:
    FakeSMTP.instances.clear()
    _email(starttls=False).notify(Notification("etl_failed", "s", "b"))
    # No SMTP connection attempted at all — plaintext AUTH is refused before dialing out.
    assert FakeSMTP.instances == []


def test_login_proceeds_over_starttls() -> None:
    FakeSMTP.instances.clear()
    _email(starttls=True).notify(Notification("etl_failed", "s", "b"))
    smtp = FakeSMTP.instances[-1]
    assert smtp.tls is True
    assert smtp.login_args == ("ugk@uge.uz", "relay-secret")


def test_implicit_ssl_path_is_used_and_login_succeeds() -> None:
    FakeSMTP.instances.clear()
    _email(ssl=True, smtp_ssl_factory=FakeSMTP).notify(Notification("etl_failed", "s", "b"))
    smtp = FakeSMTP.instances[-1]
    assert smtp.ssl_context is not None
    assert smtp.tls is False  # STARTTLS is never called on the implicit-TLS path
    assert smtp.login_args == ("ugk@uge.uz", "relay-secret")
    assert smtp.sent


def test_recipient_with_header_injection_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match=r"a@b\.uz"):
        _email(recipients=["a@b.uz\r\nBcc: x@y"])
