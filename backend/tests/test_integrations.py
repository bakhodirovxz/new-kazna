import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from app.admin import integrations_service as svc
from app.admin.dwh_schemas import IntegrationOut, IntegrationUpdate
from app.auth.context import AuthContext
from app.auth.permissions import PERMISSIONS
from app.core import integrations, keystore, sysconfig
from app.core.config import Settings
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session
from app.core.errors import ValidationFailed
from app.core.request_meta import ClientMeta
from app.main import create_app
from tests.helpers import SeedUser, clear_setting, login

META = ClientMeta(ip=None, ua=None, request_id=None)
PLAIN = "Relay-Pa55word!"
API = "/api/v1/admin/integrations"


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.integration_credentials"))
        conn.execute(text("DELETE FROM core.integration_checks"))
    for key in integrations.INTEGRATIONS["smtp"].fields:
        clear_setting(key)


@pytest.fixture
def actor(make_user: Callable[..., SeedUser]) -> AuthContext:
    user = make_user("admin")
    return AuthContext(user_id=user.id, username=user.username, full_name="A",
                       role_code="admin", permissions=frozenset(PERMISSIONS), branch_ids=None,
                       session_id=uuid.uuid4())


@pytest.fixture
def no_step_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """Step-up 3-vazifada tekshirilgan; bu yerda sir mantig'i."""
    monkeypatch.setattr(svc, "require_step_up", lambda *args, **kwargs: None)


def _update(actor: AuthContext, **body: Any) -> IntegrationOut:
    with new_session() as s:
        return svc.update_integration(
            s, actor, "smtp", IntegrationUpdate(reason="Заявка ИТ-42", otp="000000", **body), META)


def _state(out: IntegrationOut) -> str:
    return next(s.state for s in out.secrets if s.name == "smtp.password")


def _audit() -> dict[str, Any]:
    with get_engine("app").connect() as conn:
        return dict(conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.integration.updated' "
            "ORDER BY id DESC LIMIT 1")).scalar_one())


@pytest.mark.usefixtures("no_step_up")
def test_secret_is_encrypted_and_never_returned_or_audited(actor: AuthContext) -> None:
    out = _update(actor, values={"smtp.host": "relay.uge.uz", "smtp.port": 587},
                  secrets={"smtp.password": PLAIN})
    assert PLAIN not in out.model_dump_json() and _state(out) == "panel"
    with get_engine("app").connect() as conn:
        blob = conn.execute(text("SELECT value_enc FROM core.integration_credentials "
                                 "WHERE name = 'smtp.password'")).scalar_one()
        assert PLAIN.encode() not in bytes(blob)
        assert keystore.decrypt_str(Purpose.INTEGRATION, blob,
                                    "core.integration_credentials.value_enc:smtp.password") == PLAIN
        assert integrations.secret(conn, "smtp.password") == PLAIN
    details = _audit()
    assert PLAIN not in json.dumps(details, ensure_ascii=False)
    assert details["secrets"] == [{"name": "smtp.password", "action": "set"}]
    assert details["reason"] == "Заявка ИТ-42"
    assert {c["key"] for c in details["changes"]} == {"smtp.host", "smtp.port"}


@pytest.mark.usefixtures("no_step_up")
@pytest.mark.parametrize(("key", "other"), [("smtp.host", "mail.evil.example"),
                                            ("smtp.port", 2525)])
def test_endpoint_change_clears_panel_secret(actor: AuthContext, key: str, other: Any) -> None:
    _update(actor, values={"smtp.host": "relay.uge.uz", "smtp.port": 587},
            secrets={"smtp.password": PLAIN})
    out = _update(actor, values={key: other})
    assert _state(out) == "none"
    assert _audit()["secrets"] == [{"name": "smtp.password", "action": "cleared_endpoint_changed"}]
    kept = _update(actor, values={"smtp.host": "relay.uge.uz", "smtp.port": 587},
                   secrets={"smtp.password": PLAIN})
    assert _state(_update(actor, values={"smtp.user": "ugk"})) == _state(kept) == "panel"


@pytest.mark.usefixtures("no_step_up")
@pytest.mark.parametrize(("key", "value"), [("smtp.host", "relay.uge.uz"), ("smtp.port", 2525)])
def test_env_secret_not_used_once_endpoint_is_set_in_panel(
    actor: AuthContext, monkeypatch: pytest.MonkeyPatch, key: str, value: Any
) -> None:
    monkeypatch.setattr(integrations, "get_settings",
                        lambda: Settings(smtp_password=SecretStr("env-secret")))
    with get_engine("app").connect() as conn:
        assert integrations.secret(conn, "smtp.password") == "env-secret"
        assert integrations.secret_state(conn, "smtp.password")[0] == "env"
    _update(actor, values={key: value})
    with get_engine("app").connect() as conn:
        assert integrations.secret(conn, "smtp.password") == ""
        assert integrations.secret_state(conn, "smtp.password")[0] == "none"


@pytest.mark.usefixtures("no_step_up")
def test_password_without_tls_is_rejected_and_rolled_back(actor: AuthContext) -> None:
    with pytest.raises(ValidationFailed) as exc:
        _update(actor, values={"smtp.host": "relay.uge.uz", "smtp.starttls": False,
                               "smtp.ssl": False}, secrets={"smtp.password": PLAIN})
    assert (exc.value.code, exc.value.params["fields"]) == ("insecure_smtp", ["smtp.starttls"])
    with get_engine("app").connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM core.integration_credentials")) \
            .scalar_one() == 0
        assert sysconfig.current(conn, "smtp.host") == ""


@pytest.mark.usefixtures("no_step_up")
@pytest.mark.parametrize(("body", "field"), [
    ({"values": {"smtp.port": 0}}, "smtp.port"),
    ({"values": {"builds.keep": 3}}, "builds.keep"),
    ({"secrets": {"smtp.password": "a\r\nb"}}, "smtp.password"),
    ({"secrets": {"onec.password": "x"}}, "onec.password"),
])
def test_bad_values_and_unknown_names_are_422(
    actor: AuthContext, body: dict[str, Any], field: str
) -> None:
    with pytest.raises(ValidationFailed) as exc:
        _update(actor, **body)
    assert exc.value.params["fields"] == [field]


def test_missing_reason_is_422_before_step_up(actor: AuthContext) -> None:
    with pytest.raises(ValidationFailed) as exc, new_session() as s:
        svc.update_integration(s, actor, "smtp",
                               IntegrationUpdate(values={"smtp.port": 587}), META)
    assert exc.value.code == "reason_required"


def test_check_request_is_deduplicated(actor: AuthContext) -> None:
    with new_session() as s:
        first = svc.request_check(s, actor, "smtp", META)
        second = svc.request_check(s, actor, "smtp", META)
    assert first.id == second.id and first.status == "pending"


def test_http_flow_requires_permission_and_totp(make_user: Callable[..., SeedUser]) -> None:
    admin = make_user("admin")
    with TestClient(create_app(), base_url="https://testserver") as client:
        login(client, admin)
        listed = client.get(API).json()
        assert [i["name"] for i in listed] == ["smtp", "hr"]
        assert listed[0]["endpoint"] == ["smtp.host", "smtp.port"]
        body = {"values": {"smtp.host": "relay.uge.uz"}, "secrets": {"smtp.password": PLAIN},
                "reason": "Заявка ИТ-42"}
        assert client.put(f"{API}/smtp", json=body).json()["error"]["code"] == "step_up_required"
        r = client.put(f"{API}/smtp", json={**body, "otp": admin.next_code()})
        assert r.status_code == 200, r.text
        assert PLAIN not in r.text
        check = client.post(f"{API}/smtp/check")
        assert check.status_code == 202
        assert client.get(f"{API}/checks/{check.json()['id']}").json()["status"] == "pending"
        assert client.put(f"{API}/nope", json=body).status_code == 404
    with TestClient(create_app(), base_url="https://testserver") as other:
        login(other, make_user("rukovodstvo"))
        assert other.get(API).status_code == 403
