import json
from collections.abc import Callable, Iterator
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.auth import service
from app.core.db import apply_rls, get_engine, new_session
from app.main import app, create_app
from tests.helpers import DEFAULT_PASSWORD, SeedUser


@pytest.fixture
def rls_probe() -> Iterator[None]:
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS core.rls_probe"))
        conn.execute(text("CREATE TABLE core.rls_probe (id int, branch_id int NOT NULL)"))
        conn.execute(text("INSERT INTO core.rls_probe VALUES (1, 0), (2, 1), (3, 2)"))
        conn.execute(text("ALTER TABLE core.rls_probe ENABLE ROW LEVEL SECURITY"))
        conn.execute(text("ALTER TABLE core.rls_probe FORCE ROW LEVEL SECURITY"))
        conn.execute(
            text("CREATE POLICY p ON core.rls_probe USING (core.rls_branch_ok(branch_id))")
        )
        conn.execute(text("GRANT SELECT ON core.rls_probe TO ugk_app"))
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DROP TABLE core.rls_probe"))


def _visible(scope: frozenset[int] | str | None) -> list[int]:
    with new_session() as s:
        if scope != "unset":
            apply_rls(s, scope)  # type: ignore[arg-type]
        return sorted(s.execute(text("SELECT id FROM core.rls_probe")).scalars())


@pytest.mark.usefixtures("rls_probe")
def test_rls_scopes() -> None:
    assert _visible("unset") == []
    assert _visible(frozenset()) == []
    assert _visible(frozenset({1})) == [2]
    assert _visible(frozenset({1, 2})) == [2, 3]
    assert _visible(None) == [1, 2, 3]


@pytest.mark.usefixtures("rls_probe")
def test_rls_setting_is_transaction_local() -> None:
    with new_session() as s:
        apply_rls(s, None)
        assert len(s.execute(text("SELECT id FROM core.rls_probe")).all()) == 3
        s.commit()
        assert s.execute(text("SELECT id FROM core.rls_probe")).all() == []


def test_app_role_cannot_create_tables() -> None:
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("CREATE TABLE core.hack (id int)"))


def test_app_role_has_no_bypassrls() -> None:
    with new_session() as s:
        row = s.execute(
            text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")
        ).one()
    assert row == (False, False)


def test_readyz_reports_db() -> None:
    with TestClient(create_app(), base_url="https://testserver") as client:
        response = client.get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["db"] is True


def test_etl_engine_hides_parameters() -> None:
    """Fix r1, I1: ETL bog'langan parametrlarida INN/hisob kabi sezgir qiymatlar
    yuradi — SQLAlchemy istisnolari ularni logga/xabarga chiqarmasligi kerak."""
    assert get_engine("etl").hide_parameters is True
    assert get_engine("app").hide_parameters is False
    assert get_engine("migrator").hide_parameters is False


def test_etl_engine_does_not_leak_bound_value_on_error() -> None:
    """Fix r2, Minor 3: haqiqiy bog'langan parametr — `hide_parameters` faqat SQLAlchemy o'zi
    xato matniga qo'shadigan "[parameters: ...]" qismini nazorat qiladi (Postgres'ning o'z
    server-side xato DETAIL'ini emas — masalan `CAST('x' AS int)`dagi kabi "invalid input
    syntax" xatolari qiymatni serverning o'zi qaytaradi, hide_parameters'dan qat'i nazar —
    shu sababli xato SQL STRUKTURASI bilan bog'liq, qiymat bilan emas, qilib tanlangan:
    mavjud bo'lmagan jadval — Postgres qiymatni hech qachon aks ettirmaydi, faqat SQLAlchemy
    o'zi qo'shadi). Avval `app` ulanishida XATO XABARIDA QIYMAT CHIQISHINI tasdiqlaymiz (aks
    holda test hech narsani isbotlamas edi), keyin `etl` ulanishida chiqmasligini."""
    secret = "super-secret-inn-value-should-not-leak"

    with get_engine("app").connect() as conn, pytest.raises(DBAPIError) as app_exc:
        conn.execute(text("SELECT :v FROM core.no_such_table_xyz"), {"v": secret})
    assert secret in str(app_exc.value)

    with get_engine("etl").connect() as conn, pytest.raises(DBAPIError) as etl_exc:
        conn.execute(text("SELECT :v FROM core.no_such_table_xyz"), {"v": secret})
    assert secret not in str(etl_exc.value)


def test_write_is_committed_before_response_is_sent(
    make_user: Callable[..., SeedUser],
) -> None:
    """Hotfix C2: `get_db` commit'i javob yuborilishidan OLDIN bo'lishi shart (read-your-writes).

    Xom ASGI chaqiruvi: javob tanasi `send`ga kelgan paytda (dependency teardown hali
    ishlamagan bo'lishi mumkin) alohida ulanish login yaratgan challenge'ni ko'rishi kerak.
    TestClient/httpx teardown tugashini kutib qaytadi — shuning uchun ular buni ko'rmaydi.
    Middleware'lar sof ASGI, `send` bloklovchi: tekshiruv paytida teardown ishlay olmaydi.
    """
    user = make_user()
    seen: list[bool] = []
    body = json.dumps({"username": user.username, "password": DEFAULT_PASSWORD}).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "https", "path": "/api/v1/auth/login", "raw_path": b"/api/v1/auth/login",
        "query_string": b"", "root_path": "", "server": ("testserver", 443),
        "client": ("10.0.0.9", 1234),
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode())],
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.body":
            token = json.loads(message["body"])["mfa_token"]
            with get_engine("migrator").connect() as conn:
                seen.append(conn.execute(
                    text("SELECT count(*) FROM core.mfa_challenges WHERE token_hmac = :h"),
                    {"h": service._challenge_hmac(token)},
                ).scalar_one() == 1)

    anyio.run(app, scope, receive, send)
    assert seen == [True]

