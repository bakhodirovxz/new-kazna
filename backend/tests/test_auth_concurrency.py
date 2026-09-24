"""Fix round 1 — I1/I2: parallel urinishlar lost-update'siz ketma-ketlashishi kerak.

Har oqim o'z DB sessiyasiga ega (haqiqiy parallel tranzaksiyalarni simulyatsiya qiladi);
`threading.Barrier` bilan bir vaqtda boshlanishi ta'minlanadi (determinizm/tezlik uchun —
qulflar baribir ketma-ketlikni majburlaydi, lekin barrier haqiqatan ham bir vaqtda
urinilishini kafolatlaydi).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.auth import service
from app.auth.models import MfaChallenge, User
from app.core import ratelimit
from app.core.db import new_session
from app.core.errors import AuthError
from app.core.request_meta import ClientMeta
from tests.helpers import SeedUser

_META = ClientMeta(ip="10.0.0.9", ua="pytest-concurrency", request_id="concurrency-test")


def test_parallel_wrong_passwords_lock_deterministically(
    make_user: Callable[..., SeedUser],
) -> None:
    """I1: `login()` endi foydalanuvchi qatorini `FOR UPDATE` bilan o'qiydi — 10 ta parallel
    noto'g'ri urinish yo'qolgan yangilanishsiz ketma-ketlashadi va aynan 5-chi muvaffaqiyatli
    hisoblashda hisob bloklanadi (qolganlari "locked" sababi bilan hisoblagichni oshirmaydi)."""
    user = make_user()
    n = 10
    barrier = threading.Barrier(n)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt() -> None:
        barrier.wait()
        db = new_session()
        try:
            service.login(db, user.username, "Wrong-Password-1!", _META, datetime.now(UTC))
        except AuthError as exc:
            with lock:
                outcomes.append(exc.code)
        finally:
            db.close()

    threads = [threading.Thread(target=attempt) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(outcomes) == n
    assert set(outcomes) == {"invalid_credentials"}

    with new_session() as s:
        row = s.execute(select(User).where(User.id == user.id)).scalar_one()
        assert row.failed_logins == 0
        assert row.locked_until is not None and row.locked_until > datetime.now(UTC)

    ratelimit.reset("login_ip", _META.ip or "unknown")  # bu tekshiruv o'z limitidan mustaqil
    db = new_session()
    try:
        service.login(db, user.username, user.password, _META, datetime.now(UTC))
        raise AssertionError("locked bo'lgan hisob bilan login muvaffaqiyatli bo'lmasligi kerak")
    except AuthError as exc:
        assert exc.code == "invalid_credentials"
    finally:
        db.close()


def test_parallel_mfa_verify_same_code_exactly_one_succeeds(
    make_user: Callable[..., SeedUser],
) -> None:
    """I2: ikkita mustaqil ochiq "verify" challenge (bitta foydalanuvchi), bir xil TOTP
    kodi bilan parallel tasdiqlanadi. `_load_challenge` endi foydalanuvchi qatorini ham
    qulflaydi — g'olib bo'lmagan oqim yangilangan `totp_last_step`ni ko'radi va
    invalid_mfa_code bilan rad etiladi (ikkalasi ham 200 bo'lib qolishining oldi olinadi)."""
    user = make_user()
    code = user.next_code()
    now = datetime.now(UTC)
    tokens = [f"concurrency-verify-{i}-{user.id}" for i in range(2)]
    with new_session() as s:
        for token in tokens:
            s.add(
                MfaChallenge(
                    token_hmac=service._challenge_hmac(token),
                    user_id=user.id,
                    kind="verify",
                    created_at=now,
                    expires_at=now + timedelta(minutes=5),
                )
            )
        s.commit()

    barrier = threading.Barrier(2)
    results: dict[str, str] = {}
    lock = threading.Lock()

    def attempt(token: str, key: str) -> None:
        barrier.wait()
        db = new_session()
        try:
            service.verify_mfa(db, token, code, _META, datetime.now(UTC))
            db.commit()
            with lock:
                results[key] = "200"
        except AuthError as exc:
            db.rollback()
            with lock:
                results[key] = exc.code
        finally:
            db.close()

    threads = [
        threading.Thread(target=attempt, args=(tokens[0], "a")),
        threading.Thread(target=attempt, args=(tokens[1], "b")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    outcomes = list(results.values())
    assert len(outcomes) == 2
    assert outcomes.count("200") == 1
    assert outcomes.count("invalid_mfa_code") == 1
