from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.audit import router as audit_router
from app.audit.router import _cell
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


# Fix round 1 (finding 1): leading whitespace/NBSP before a formula trigger must not bypass
# the CSV formula-injection guard, and the escaped cell must keep the ORIGINAL value.
def test_cell_catches_leading_whitespace_formula_injection() -> None:
    assert _cell(" =1+1") == "' =1+1"
    assert _cell("\t=cmd") == "'\t=cmd"
    assert _cell(" @x") == "' @x"
    assert _cell("-5") == "'-5"
    assert _cell("normal") == "normal"
    assert _cell(" =1+1") == "' =1+1"


# Fix round 1 (finding 2): a full-table HMAC chain scan must be rate limited — per user and
# globally — since it is not a cheap operation.
def test_verify_rate_limited_per_user(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user("admin"))
    for _ in range(3):
        assert client.post("/api/v1/audit/verify").status_code == 200
    r = client.post("/api/v1/audit/verify")
    assert r.status_code == 429
    assert r.headers.get("retry-after") is not None


# Fix round 1 (minor): the export must flag truncation via a response header when the row
# cap is hit, without leaking whether the cap was hit into the CSV body itself.
def test_export_csv_truncation_header(
    client: TestClient, make_user: Callable[..., SeedUser], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit_router, "EXPORT_LIMIT", 2)
    auditor = make_user("vnutr_kontrol")
    login(client, auditor)
    for _ in range(3):
        record(AuditEvent(action=AuditAction.USER_UPDATED, user_id=auditor.id))
    params = {"user_id": auditor.id, "action": "admin.user.updated"}
    r = client.get("/api/v1/audit/export.csv", params=params)
    assert r.status_code == 200
    assert r.headers.get("x-export-truncated") == "true"
    body_rows = r.content.decode("utf-8").strip("﻿").strip().splitlines()
    assert len(body_rows) - 1 == 2  # header + EXPORT_LIMIT data rows


def test_export_csv_no_truncation_header_when_under_limit(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    auditor = make_user("vnutr_kontrol")
    login(client, auditor)
    r = client.get("/api/v1/audit/export.csv", params={"user_id": auditor.id})
    assert r.status_code == 200
    assert "x-export-truncated" not in r.headers
