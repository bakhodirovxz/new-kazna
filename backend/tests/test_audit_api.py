from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.audit.service import AuditAction, AuditEvent, record
from app.main import create_app
from tests.helpers import SeedUser, login


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


def test_requires_audit_permission(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("rukovodstvo"))
    assert client.get("/api/v1/audit").status_code == 403


def test_list_filters_and_decrypts_ip(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    auditor = make_user("vnutr_kontrol")
    login(client, auditor)
    record(AuditEvent(action=AuditAction.USER_BLOCKED, user_id=auditor.id, ip="172.16.5.9",
                      object_type="user", object_id="42"))
    params = {"user_id": auditor.id, "action": "admin.user"}
    page = client.get("/api/v1/audit", params=params).json()
    assert page["total"] >= 1
    item = page["items"][0]
    assert item["action"] == "admin.user.blocked"
    assert item["ip"] == "172.16.5.9"
    assert item["username"] == auditor.username


def test_export_csv_is_safe_and_audited(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    auditor = make_user("vnutr_kontrol")
    login(client, auditor)
    record(AuditEvent(action=AuditAction.USER_UPDATED, user_id=auditor.id,
                      object_type="user", object_id="=HYPERLINK(\"http://x\")"))
    r = client.get("/api/v1/audit/export.csv", params={"user_id": auditor.id})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("﻿")
    assert "id;ts;username;action" in text
    assert "'=HYPERLINK" in text
    params = {"user_id": auditor.id, "action": "audit.exported"}
    page = client.get("/api/v1/audit", params=params).json()
    assert page["total"] >= 1


def test_verify_endpoint(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("admin"))
    r = client.post("/api/v1/audit/verify")
    assert r.status_code == 200
    assert r.json()["ok"] is True
