"""Testlar uchun foydalanuvchi va sessiya yaratish yordamchilari."""

from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import sessions
from app.auth.context import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.auth.models import Position, PositionBranch, Role, User
from app.auth.passwords import hash_password
from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import new_session

DEFAULT_PASSWORD = "Sinov-Kalit-2026!"
_counter = itertools.count()


@dataclass
class SeedUser:
    id: int
    username: str
    password: str
    totp_secret: str | None
    _step: int = field(default=0)

    def next_code(self) -> str:
        """Har chaqiruvda keyingi TOTP qadami — replay himoyasi testlarni yiqitmasligi uchun.

        Fix r1 (M11): pastki chegara `now_step - 1` emas, `now_step` — aks holda 30-soniyalik
        chegara kod hisoblangandan keyin, server tekshirgunga qadar kesib o'tilsa (flake), kod
        server oynasidan (odatda ±1 qadam) tashqariga chiqib ketishi mumkin edi.
        """
        assert self.totp_secret is not None
        now_step = int(time.time()) // 30
        self._step = max(self._step + 1, now_step)
        if self._step > now_step + 1:
            time.sleep(30 - time.time() % 30 + 0.1)
            return self.next_code()
        return str(pyotp.TOTP(self.totp_secret).at(self._step * 30))


def create_user(
    role: str = "admin",
    *,
    branch_ids: tuple[int, ...] = (),
    totp: bool = True,
    must_change: bool = False,
    password: str = DEFAULT_PASSWORD,
) -> SeedUser:
    username = f"u{next(_counter)}_{uuid.uuid4().hex[:8]}"
    with new_session() as s:
        role_id = s.execute(select(Role.id).where(Role.code == role)).scalar_one()
        position = Position(code=f"p_{username}", name=f"Test {role}", role_id=role_id)
        s.add(position)
        s.flush()
        for branch in branch_ids:
            s.add(PositionBranch(position_id=position.id, branch_id=branch))
        user = User(
            username=username,
            full_name="Тестовый Пользователь",
            position_id=position.id,
            password_hash=hash_password(password),
            password_changed_at=datetime.now(UTC),
            must_change_password=must_change,
            totp_enabled=totp,
        )
        s.add(user)
        s.flush()
        secret = pyotp.random_base32(32) if totp else None
        if secret:
            user.totp_secret_enc = keystore.encrypt_str(
                Purpose.MFA, secret, f"core.users.totp_secret_enc:{user.id}"
            )
        s.commit()
        return SeedUser(id=user.id, username=username, password=password, totp_secret=secret)


def issue_session(user_id: int) -> tuple[str, str, uuid.UUID]:
    with new_session() as s:
        new = sessions.create(s, user_id, "10.0.0.1", "pytest", datetime.now(UTC))
        s.commit()
    return new.token, new.csrf, new.id


def use_session(client: TestClient, token: str, csrf: str) -> TestClient:
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf)
    client.headers[CSRF_HEADER] = csrf
    return client


def login(client: TestClient, user: SeedUser) -> TestClient:
    r = client.post(
        "/api/v1/auth/login", json={"username": user.username, "password": user.password}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next"] == "mfa_verify", body
    r = client.post(
        "/api/v1/auth/2fa/verify",
        json={"mfa_token": body["mfa_token"], "code": user.next_code()},
    )
    assert r.status_code == 200, r.text
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    return client
