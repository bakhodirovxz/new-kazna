import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.auth.models import Role, RolePermission
from app.auth.permissions import PERMISSIONS, Perm
from app.auth.seed import sync_reference
from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session
from app.core.reencrypt import REGISTRY
from app.etl.db import etl_transaction

AAD = "core.integration_credentials.value_enc:t.secret"


@pytest.fixture(autouse=True)
def _clean() -> None:
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.integration_credentials WHERE name LIKE 't.%'"))


def test_credentials_grants_and_ciphertext_check() -> None:
    blob = keystore.encrypt_str(Purpose.INTEGRATION, "pw", AAD)
    with get_engine("app").begin() as conn:
        conn.execute(text("INSERT INTO core.integration_credentials (name, value_enc) "
                          "VALUES ('t.secret', :b)"), {"b": blob})
        conn.execute(text("UPDATE core.integration_credentials SET updated_at = now() "
                          "WHERE name = 't.secret'"))
    with etl_transaction() as conn:
        assert conn.execute(text("SELECT count(*) FROM core.integration_credentials "
                                 "WHERE name = 't.secret'")).scalar_one() == 1
    with pytest.raises(ProgrammingError), etl_transaction() as conn:
        conn.execute(text("DELETE FROM core.integration_credentials"))
    with pytest.raises(IntegrityError), get_engine("app").begin() as conn:
        conn.execute(text("INSERT INTO core.integration_credentials (name, value_enc) "
                          "VALUES ('t.short', '\\x01')"))


def test_checks_table_accepts_only_known_statuses() -> None:
    with get_engine("app").begin() as conn:
        row_id = conn.execute(text("INSERT INTO core.integration_checks (name, requested_by) "
                                   "VALUES ('smtp', 1) RETURNING id")).scalar_one()
        conn.execute(text("UPDATE core.integration_checks SET status = 'ok' WHERE id = :i"),
                     {"i": row_id})
    with pytest.raises(IntegrityError), get_engine("app").begin() as conn:
        conn.execute(text("UPDATE core.integration_checks SET status = 'weird' WHERE id = :i"),
                     {"i": row_id})


def test_credentials_column_is_reencrypted_by_app_role() -> None:
    col = next(c for c in REGISTRY if c.table == "core.integration_credentials")
    assert (col.pk, col.column, col.purpose, col.role) == (
        "name", "value_enc", Purpose.INTEGRATION, "app")
    assert col.aad("t.secret") == AAD


def test_new_permissions_have_titles() -> None:
    assert PERMISSIONS[Perm.ADMIN_SECURITY.value] == "Администрирование: политика безопасности"
    assert PERMISSIONS[Perm.ADMIN_INTEGRATIONS.value] == (
        "Администрирование: интеграции и учётные данные")


def _admin_has(s: Session, admin_id: int, code: str) -> bool:
    return s.execute(select(RolePermission).where(
        RolePermission.role_id == admin_id, RolePermission.permission_code == code)).first() \
        is not None


def test_new_permission_is_granted_to_admin_role_once() -> None:
    code = Perm.ADMIN_SECURITY.value
    with new_session() as s:
        admin_id = s.execute(select(Role.id).where(Role.code == "admin")).scalar_one()
    with get_engine("migrator").begin() as conn:  # "eski baza": ruxsat hali yo'q
        conn.execute(text("DELETE FROM core.permissions WHERE code = :c"), {"c": code})
    try:
        with new_session() as s:
            sync_reference(s)
            s.commit()
            assert _admin_has(s, admin_id, code)
            s.execute(delete(RolePermission).where(RolePermission.role_id == admin_id,
                                                   RolePermission.permission_code == code))
            s.commit()
            sync_reference(s)  # endi ruxsat mavjud — qayta berilmaydi
            s.commit()
            assert not _admin_has(s, admin_id, code)
    finally:
        with new_session() as s:
            if not _admin_has(s, admin_id, code):
                s.add(RolePermission(role_id=admin_id, permission_code=code))
                s.commit()
