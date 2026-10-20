import json
import secrets
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update

from app.auth import service
from app.auth.context import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, AuthContext
from app.auth.models import MfaChallenge, User, UserSession
from app.core import keystore, ratelimit
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session
from app.core.errors import ValidationFailed
from app.core.request_meta import ClientMeta
from app.main import create_app
from tests.helpers import DEFAULT_PASSWORD, SeedUser, login

NEW_PASSWORD = "Yangi-Mustahkam-77#"
_META = ClientMeta(ip="10.0.0.1", ua="pytest", request_id="fix-r1-test")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


def _login_step(client: TestClient, username: str, password: str = DEFAULT_PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def _audit_actions(user_id: int) -> list[str]:
    with get_engine("app").connect() as conn:
        return list(
            conn.execute(
                text("SELECT action FROM core.audit_log WHERE user_id = :u ORDER BY id"),
                {"u": user_id},
            ).scalars()
        )


def _audit_details(user_id: int) -> list[dict[str, object]]:
    with get_engine("app").connect() as conn:
        rows = conn.execute(
            text("SELECT details FROM core.audit_log WHERE user_id = :u ORDER BY id"),
            {"u": user_id},
        ).mappings().all()
    return [dict(row["details"]) for row in rows]


def _make_challenge(
    user_id: int, kind: str, *, now: datetime, pending_secret: str | None = None
) -> str:
    """Fix round 1 (I2/M7): bir foydalanuvchi uchun bir nechta bir vaqtda ochiq challenge
    yaratadi — `service.login()` orqali emas (u endi eskilarini bekor qiladi, I3), balki
    to'g'ridan-to'g'ri DB'ga, faqat shu maqsad uchun."""
    token = secrets.token_urlsafe(32)
    token_hmac = service._challenge_hmac(token)
    pending_enc = None
    if pending_secret is not None:
        aad = service._pending_secret_aad(token_hmac)
        pending_enc = keystore.encrypt_str(Purpose.MFA, pending_secret, aad)
    with new_session() as s:
        s.add(
            MfaChallenge(
                token_hmac=token_hmac,
                user_id=user_id,
                kind=kind,
                created_at=now,
                expires_at=now + timedelta(minutes=5),
                pending_secret_enc=pending_enc,
            )
        )
        s.commit()
    return token


def _dummy_ctx(user_id: int, username: str) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        username=username,
        full_name="Test",
        role_code="x",
        permissions=frozenset(),
        branch_ids=None,
        session_id=uuid.uuid4(),
    )


def test_unknown_user_is_generic_401(client: TestClient) -> None:
    r = _login_step(client, "no_such_user")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_full_login_sets_hardened_cookies(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user("economist_filiala", branch_ids=(4,))
    r = _login_step(client, user.username)
    assert r.status_code == 200 and r.json()["next"] == "mfa_verify"
    r = client.post(
        "/api/v1/auth/2fa/verify",
        json={"mfa_token": r.json()["mfa_token"], "code": user.next_code()},
    )
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("__Host-ugk_session="))
    for attr in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert attr.lower() in session_cookie.lower()
    assert any(c.startswith("__Host-ugk_csrf=") for c in cookies)
    body = r.json()
    assert body["username"] == user.username
    assert body["branch_ids"] == [4]
    assert "section:kazna:view" in body["permissions"]
    assert _audit_actions(user.id)[-2:] == ["auth.password.ok", "auth.login.ok"]


def test_login_username_is_normalized(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    r = _login_step(client, f"  {user.username.upper()} ")
    assert r.status_code == 200


def test_lockout_after_five_failures(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    for _ in range(5):
        assert _login_step(client, user.username, "Wrong-Password-1!").status_code == 401
    assert _login_step(client, user.username).status_code == 401  # to'g'ri parol ham rad
    with new_session() as s:
        s.execute(
            update(User)
            .where(User.id == user.id)
            .values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        s.commit()
    assert _login_step(client, user.username).status_code == 200


def test_inactive_user_cannot_login(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    with new_session() as s:
        s.execute(update(User).where(User.id == user.id).values(is_active=False))
        s.commit()
    assert _login_step(client, user.username).json()["error"]["code"] == "invalid_credentials"


def test_challenge_dies_after_five_wrong_codes(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    token = _login_step(client, user.username).json()["mfa_token"]
    for _ in range(5):
        r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": "000000"})
        assert r.json()["error"]["code"] == "invalid_mfa_code"
    r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": user.next_code()})
    assert r.json()["error"]["code"] == "mfa_expired"


def test_totp_code_cannot_be_replayed(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    code = user.next_code()
    t1 = _login_step(client, user.username).json()["mfa_token"]
    r1 = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": t1, "code": code})
    assert r1.status_code == 200
    t2 = _login_step(client, user.username).json()["mfa_token"]
    r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": t2, "code": code})
    assert r.json()["error"]["code"] == "invalid_mfa_code"


def test_enroll_flow_and_backup_codes(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user(totp=False)
    r = _login_step(client, user.username)
    assert r.json()["next"] == "mfa_enroll"
    token = r.json()["mfa_token"]
    # verify-turdagi endpoint enroll tokenini qabul qilmaydi
    wrong_kind = client.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": "123456"}
    )
    assert wrong_kind.json()["error"]["code"] == "mfa_expired"
    start = client.post("/api/v1/auth/2fa/enroll/start", json={"mfa_token": token}).json()
    assert start["otpauth_uri"].startswith("otpauth://totp/UGEKAZNA:")
    assert start["qr_svg_data_uri"].startswith("data:image/svg+xml")
    otp = pyotp.TOTP(start["secret"])
    bad = client.post(
        "/api/v1/auth/2fa/enroll/confirm", json={"mfa_token": token, "code": "000000"}
    )
    assert bad.json()["error"]["code"] == "invalid_mfa_code"
    ok = client.post(
        "/api/v1/auth/2fa/enroll/confirm", json={"mfa_token": token, "code": otp.now()}
    )
    assert ok.status_code == 200
    codes = ok.json()["backup_codes"]
    assert len(codes) == 10
    assert "auth.mfa.enrolled" in _audit_actions(user.id)

    # Endi login verify'ga olib boradi; zaxira kod bir marta ishlaydi.
    fresh = TestClient(client.app, base_url="https://testserver")
    t = _login_step(fresh, user.username).json()
    assert t["next"] == "mfa_verify"
    r_used = fresh.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": t["mfa_token"], "code": codes[0].lower()}
    )
    assert r_used.status_code == 200
    t = _login_step(fresh, user.username).json()
    r_replay = fresh.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": t["mfa_token"], "code": codes[0]}
    )
    assert r_replay.status_code == 401


def test_me_and_logout(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    login(client, user)
    assert client.get("/api/v1/auth/me").json()["username"] == user.username
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_forced_password_change(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user(must_change=True)
    login(client, user)
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is True
    sessions_r = client.get("/api/v1/auth/sessions")
    assert sessions_r.json()["error"]["code"] == "password_change_required"

    weak = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "short"},
    )
    assert weak.status_code == 422
    assert "password_too_short" in weak.json()["error"]["params"]["problems"]

    wrong = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "Nope-Nope-123!", "new_password": NEW_PASSWORD},
    )
    assert wrong.json()["error"]["code"] == "invalid_current_password"

    same = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
    )
    assert same.json()["error"]["params"]["problems"] == ["password_reused"]

    other = TestClient(client.app, base_url="https://testserver")
    login(other, user)
    ok = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert ok.status_code == 204
    assert client.get("/api/v1/auth/sessions").status_code == 200  # joriy sessiya tirik
    assert other.get("/api/v1/auth/me").status_code == 401  # boshqasi bekor
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is False


def test_sessions_list_and_revoke(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    other = TestClient(client.app, base_url="https://testserver")
    login(other, user)
    login(client, user)
    listed = client.get("/api/v1/auth/sessions").json()
    assert len(listed) >= 2
    current = [s for s in listed if s["current"]]
    assert len(current) == 1 and current[0]["ip"] == "testclient"
    victim = next(s for s in listed if not s["current"])
    assert client.delete(f"/api/v1/auth/sessions/{victim['id']}").status_code == 204
    assert other.get("/api/v1/auth/me").status_code == 401


def test_cannot_revoke_foreign_session(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    a, b = make_user(), make_user()
    other = TestClient(client.app, base_url="https://testserver")
    login(other, b)
    b_session = other.get("/api/v1/auth/sessions").json()[0]["id"]
    login(client, a)
    assert client.delete(f"/api/v1/auth/sessions/{b_session}").status_code == 404


def test_csrf_header_required_for_logout(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user())
    del client.headers[CSRF_HEADER]
    assert client.post("/api/v1/auth/logout").status_code == 403
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    assert client.post("/api/v1/auth/logout").status_code == 204


# ── Fix round 1 ──────────────────────────────────────────────────────────────


def test_challenge_ttl_expired_is_mfa_expired(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """M14: muddati o'tgan challenge — hatto to'g'ri kod bilan ham — mfa_expired."""
    user = make_user()
    token = _login_step(client, user.username).json()["mfa_token"]
    with new_session() as s:
        s.execute(
            update(MfaChallenge)
            .where(MfaChallenge.token_hmac == service._challenge_hmac(token))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        s.commit()
    r = client.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": user.next_code()}
    )
    assert r.json()["error"]["code"] == "mfa_expired"


def test_login_rate_limited_after_threshold(client: TestClient) -> None:
    """M14: LOGIN_PER_IP (10/daq) dan keyin 429."""
    for _ in range(10):
        assert _login_step(client, "rl-nonexistent-user").status_code == 401
    r = _login_step(client, "rl-nonexistent-user")
    assert r.status_code == 429


def test_enroll_start_conflict_when_already_enabled(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """M14: 2FA allaqachon yoqilgan bo'lsa, (masalan ikkinchi qurilmadan qolgan) ochiq
    enroll challenge bilan `enroll/start` chaqirilsa — 409."""
    user = make_user(totp=False)
    token = _login_step(client, user.username).json()["mfa_token"]
    start = client.post("/api/v1/auth/2fa/enroll/start", json={"mfa_token": token}).json()
    otp = pyotp.TOTP(start["secret"])
    ok = client.post(
        "/api/v1/auth/2fa/enroll/confirm", json={"mfa_token": token, "code": otp.now()}
    )
    assert ok.status_code == 200

    extra_token = _make_challenge(user.id, "enroll", now=datetime.now(UTC))
    r = client.post("/api/v1/auth/2fa/enroll/start", json={"mfa_token": extra_token})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "mfa_already_enabled"


def test_password_history_depth(make_user: Callable[..., SeedUser]) -> None:
    """M14: HISTORY_DEPTH=5 — oxirgi 5 ta (joriysi + 4 tasi) parol qayta ishlatilmaydi;
    6-eng eski parol esa endi ruxsat etiladi."""
    user = make_user()
    ctx = _dummy_ctx(user.id, user.username)
    now = datetime.now(UTC)
    sequence = [DEFAULT_PASSWORD] + [f"Tarix-Kalit-{i}-Kuchli#" for i in range(1, 6)]
    current = sequence[0]
    with new_session() as s:
        for new_pw in sequence[1:]:
            ratelimit.reset("password_change_user", str(user.id))
            service.change_password(s, ctx, current, new_pw, _META, now)
            s.commit()
            current = new_pw
        # `current` == sequence[5]; sequence[1] hali 5-chuqurlik ichida — rad etiladi.
        ratelimit.reset("password_change_user", str(user.id))
        with pytest.raises(ValidationFailed) as exc:
            service.change_password(s, ctx, current, sequence[1], _META, now)
        assert exc.value.params["problems"] == ["password_reused"]
        s.rollback()
        # sequence[0] (eng birinchi) endi chuqurlikdan chiqqan — qabul qilinadi.
        ratelimit.reset("password_change_user", str(user.id))
        service.change_password(s, ctx, current, sequence[0], _META, now)
        s.commit()


def test_own_sessions_list_excludes_other_users(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """M14: /auth/sessions boshqa foydalanuvchining sessiyalarini hech qachon ko'rsatmaydi."""
    a, b = make_user(), make_user()
    other = TestClient(client.app, base_url="https://testserver")
    login(other, b)
    login(client, a)
    mine = {s["id"] for s in client.get("/api/v1/auth/sessions").json()}
    b_session_id = other.get("/api/v1/auth/sessions").json()[0]["id"]
    assert b_session_id not in mine


def test_audit_details_never_contain_secrets(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """M14: login/MFA/parol-almashtirish audit yozuvlarida parol, TOTP kod yoki tokenlar
    ochiq matnda saqlanmaydi."""
    user = make_user()
    code = user.next_code()
    r = _login_step(client, user.username)
    client.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": r.json()["mfa_token"], "code": code}
    )
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    blob = json.dumps(_audit_details(user.id), default=str)
    for secret in (DEFAULT_PASSWORD, NEW_PASSWORD, code):
        assert secret not in blob


def test_mfa_bruteforce_across_fresh_challenges_locks_account(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """I3: 5 ta noto'g'ri MFA kodi — har biri YANGI challenge'da — hisobni bloklaydi;
    bloklangan foydalanuvchining ochiq challenge'i to'g'ri kod bilan ham ishlamaydi."""
    user = make_user()
    last_token = ""
    for _ in range(5):
        last_token = _login_step(client, user.username).json()["mfa_token"]
        r = client.post(
            "/api/v1/auth/2fa/verify", json={"mfa_token": last_token, "code": "000000"}
        )
        assert r.json()["error"]["code"] == "invalid_mfa_code"

    with new_session() as s:
        row = s.execute(select(User).where(User.id == user.id)).scalar_one()
        assert row.failed_logins == 0
        assert row.locked_until is not None and row.locked_until > datetime.now(UTC)

    assert _login_step(client, user.username).json()["error"]["code"] == "invalid_credentials"
    r = client.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": last_token, "code": user.next_code()}
    )
    assert r.json()["error"]["code"] == "mfa_expired"


def test_new_login_challenge_invalidates_previous_one(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """I3: yangi login challenge chiqarilganda, foydalanuvchining oldingi ochiq
    challenge'i o'ldiriladi."""
    user = make_user()
    old_token = _login_step(client, user.username).json()["mfa_token"]
    _login_step(client, user.username)
    r = client.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": old_token, "code": user.next_code()}
    )
    assert r.json()["error"]["code"] == "mfa_expired"


def test_enroll_pending_secret_bound_to_challenge(make_user: Callable[..., SeedUser]) -> None:
    """M7: ikkita parallel enroll challenge — har biri o'z sirini saqlaydi; birinchisini
    tasdiqlash aynan birinchi sirni foydalanuvchiga ko'chiradi (ikkinchisini emas)."""
    user = make_user(totp=False)
    now = datetime.now(UTC)
    token1 = _make_challenge(user.id, "enroll", now=now)
    token2 = _make_challenge(user.id, "enroll", now=now)
    with new_session() as s:
        start1 = service.enroll_start(s, token1, _META, now)
        start2 = service.enroll_start(s, token2, _META, now)
        s.commit()
    assert start1.secret != start2.secret

    code1 = pyotp.TOTP(start1.secret).now()
    with new_session() as s:
        service.enroll_confirm(s, token1, code1, _META, now)
        s.commit()
    with new_session() as s:
        row = s.get(User, user.id)
        assert row is not None and row.totp_secret_enc is not None
        stored = keystore.decrypt_str(Purpose.MFA, row.totp_secret_enc, service.totp_aad(user.id))
    assert stored == start1.secret


def test_password_change_lockout_revokes_all_sessions(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """I4: 5 ta noto'g'ri joriy parol — hisobni bloklaydi va BARCHA sessiyalarni (joriysini
    ham) bekor qiladi; keyingi login ham rad etiladi."""
    user = make_user()
    login(client, user)
    for _ in range(4):
        r = client.post(
            "/api/v1/auth/password/change",
            json={"current_password": "Nope-Nope-123!", "new_password": NEW_PASSWORD},
        )
        assert r.json()["error"]["code"] == "invalid_current_password"
    assert client.get("/api/v1/auth/me").status_code == 200

    r5 = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "Nope-Nope-123!", "new_password": NEW_PASSWORD},
    )
    assert r5.json()["error"]["code"] == "invalid_current_password"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert _login_step(client, user.username).json()["error"]["code"] == "invalid_credentials"


def test_password_change_rate_limited(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """I4/M14: PASSWORD_CHANGE_PER_USER (5/15daq) dan keyin 429, natijadan qat'i nazar."""
    user = make_user()
    login(client, user)
    current = DEFAULT_PASSWORD
    for i in range(5):
        new_pw = f"Smena-Kalit-{i}-Krepkiy#"
        r = client.post(
            "/api/v1/auth/password/change",
            json={"current_password": current, "new_password": new_pw},
        )
        assert r.status_code == 204, r.text
        client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
        current = new_pw
    r = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": current, "new_password": "Yet-Another-99#"},
    )
    assert r.status_code == 429


def test_password_change_rotates_session(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """M8: parol muvaffaqiyatli almashtirilganda joriy sessiya ham aylantiriladi — eski
    cookie endi ishlamaydi, yangisi ishlaydi; parolgacha ochilgan MFA challenge ham
    endi ishlamaydi (fix r2, kam xarajatli qoida #3)."""
    user = make_user()
    login(client, user)
    old_session = client.cookies[SESSION_COOKIE]
    stale_challenge = _make_challenge(user.id, "verify", now=datetime.now(UTC))
    r = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 204
    assert client.cookies[SESSION_COOKIE] != old_session
    assert client.get("/api/v1/auth/me").status_code == 200

    stale = TestClient(client.app, base_url="https://testserver")
    stale.cookies.set(SESSION_COOKIE, old_session)
    assert stale.get("/api/v1/auth/me").status_code == 401

    r2 = client.post(
        "/api/v1/auth/2fa/verify", json={"mfa_token": stale_challenge, "code": user.next_code()}
    )
    assert r2.json()["error"]["code"] == "mfa_expired"


def test_logout_with_expired_session_clears_cookies(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """M11: sessiya endi yaroqsiz bo'lsa ham logout 204 qaytaradi va cookie'larni tozalaydi."""
    user = make_user()
    login(client, user)
    with new_session() as s:
        s.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id)
            .values(revoked_at=datetime.now(UTC))
        )
        s.commit()
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    cookies = r.headers.get_list("set-cookie")
    assert any(c.startswith("__Host-ugk_session=") for c in cookies)
    assert any(c.startswith("__Host-ugk_csrf=") for c in cookies)


def test_logout_without_session_cookie_is_204(client: TestClient) -> None:
    """M11: sessiya cookie'si umuman bo'lmasa ham logout — CSRF talab qilmasdan — 204."""
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_sessions_excludes_idle_expired(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    """M9: idle/absolyut muddati o'tgan (lekin hali bekor qilinmagan) sessiya ro'yxatda
    ko'rinmaydi."""
    user = make_user()
    other = TestClient(client.app, base_url="https://testserver")
    login(other, user)
    login(client, user)
    listed = client.get("/api/v1/auth/sessions").json()
    assert len(listed) == 2
    victim = next(s for s in listed if not s["current"])
    with new_session() as s:
        s.execute(
            update(UserSession)
            .where(UserSession.id == uuid.UUID(victim["id"]))
            .values(idle_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        s.commit()
    listed2 = client.get("/api/v1/auth/sessions").json()
    assert len(listed2) == 1
    assert listed2[0]["current"] is True


# ── Fix round 2 ──────────────────────────────────────────────────────────────


def test_unknown_username_audit_details_are_safe(client: TestClient) -> None:
    """R2-2 (M5 residual): "login" maydoniga yozilgan istalgan xom matn (hatto parolga
    o'xshab ketsa ham) audit `details`da hech qanday ko'rinishda saqlanmaydi — faqat
    barqaror fingerprint, uzunlik va (xavfsiz bo'lsa) 2 belgili maslahat."""
    raw = "Secret-Pass-2026!"
    r = _login_step(client, raw)
    assert r.json()["error"]["code"] == "invalid_credentials"
    with get_engine("app").connect() as conn:
        row = conn.execute(
            text(
                "SELECT details, details::text AS raw_text FROM core.audit_log "
                "WHERE user_id IS NULL AND action = 'auth.login.fail' "
                "ORDER BY id DESC LIMIT 1"
            )
        ).mappings().one()
    details = row["details"]
    assert details["reason"] == "unknown_user"
    assert isinstance(details["username_len"], int) and details["username_len"] == len(raw)
    assert isinstance(details["username_fp"], str) and len(details["username_fp"]) == 16
    hint = details.get("username_hint")
    assert hint is None or len(hint) <= 3  # <=2 belgi + "…"
    assert raw not in row["raw_text"]
    assert raw.lower() not in row["raw_text"].lower()
    assert "username" not in details  # xom kalit nomi ham yo'q


# ── Final review I1: fon so'rovlari idle muddatini surmaydi ──────────────────


BACKGROUND = {"X-UGK-Background": "1"}


def _idle_expires(user_id: int) -> datetime:
    with new_session() as s:
        return s.execute(
            select(UserSession.idle_expires_at).where(UserSession.user_id == user_id)
        ).scalar_one()


def _age_session(user_id: int, seconds: int) -> None:
    """last_seen/idle'ni `seconds` orqaga suradi (60 s sliding oynasidan o'tish uchun)."""
    delta = timedelta(seconds=seconds)
    with new_session() as s:
        s.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(
                last_seen_at=UserSession.last_seen_at - delta,
                idle_expires_at=UserSession.idle_expires_at - delta,
            )
        )
        s.commit()


def test_background_request_does_not_slide_idle(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    user = make_user()
    login(client, user)
    _age_session(user.id, 120)
    before = _idle_expires(user.id)
    assert client.get("/api/v1/auth/me", headers=BACKGROUND).status_code == 200
    assert _idle_expires(user.id) == before
    assert client.get("/api/v1/auth/me").status_code == 200
    assert _idle_expires(user.id) > before


def test_idle_session_expires_despite_background_polls(
    client: TestClient, make_user: Callable[..., SeedUser], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.auth import context

    user = make_user()
    login(client, user)
    real = context.datetime
    offset = timedelta()

    class Shifted(real):  # type: ignore[valid-type, misc]
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            return real.now(tz) + offset

    monkeypatch.setattr(context, "datetime", Shifted)
    for minutes in (10, 20):
        offset = timedelta(minutes=minutes)
        assert client.get("/api/v1/auth/me", headers=BACKGROUND).status_code == 200
    offset = timedelta(minutes=31)
    assert client.get("/api/v1/auth/me", headers=BACKGROUND).status_code == 401
