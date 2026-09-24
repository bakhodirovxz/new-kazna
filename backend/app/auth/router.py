"""Auth endpointlari."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Response
from sqlalchemy.orm import Session

from app.auth import service, sessions
from app.auth.context import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, Ctx, build_context, csrf_ok
from app.auth.schemas import (
    EnrollConfirmOut,
    EnrollStartOut,
    LoginIn,
    LoginOut,
    MeOut,
    MfaIn,
    MfaTokenIn,
    PasswordChangeIn,
    SessionOut,
    me_out,
)
from app.core.db import get_db
from app.core.errors import ForbiddenError
from app.core.request_meta import Meta

router = APIRouter(prefix="/auth", tags=["auth"])
DB = Annotated[Session, Depends(get_db)]


def _set_session_cookies(response: Response, new: sessions.NewSession) -> None:
    response.set_cookie(
        SESSION_COOKIE, new.token, httponly=True, secure=True, samesite="strict", path="/"
    )
    response.set_cookie(
        CSRF_COOKIE, new.csrf, httponly=False, secure=True, samesite="strict", path="/"
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=True, samesite="strict")


@router.post("/login")
def login(body: LoginIn, db: DB, meta: Meta) -> LoginOut:
    result = service.login(db, body.username, body.password, meta, datetime.now(UTC))
    return LoginOut(next=result.next, mfa_token=result.mfa_token)


@router.post("/2fa/verify")
def verify(body: MfaIn, response: Response, db: DB, meta: Meta) -> MeOut:
    now = datetime.now(UTC)
    new, user = service.verify_mfa(db, body.mfa_token, body.code, meta, now)
    _set_session_cookies(response, new)
    return me_out(build_context(db, user, new.id, now))


@router.post("/2fa/enroll/start")
def enroll_start(body: MfaTokenIn, db: DB, meta: Meta) -> EnrollStartOut:
    start = service.enroll_start(db, body.mfa_token, meta, datetime.now(UTC))
    return EnrollStartOut(
        otpauth_uri=start.otpauth_uri, qr_svg_data_uri=start.qr_svg_data_uri, secret=start.secret
    )


@router.post("/2fa/enroll/confirm")
def enroll_confirm(body: MfaIn, response: Response, db: DB, meta: Meta) -> EnrollConfirmOut:
    now = datetime.now(UTC)
    new, user, codes = service.enroll_confirm(db, body.mfa_token, body.code, meta, now)
    _set_session_cookies(response, new)
    return EnrollConfirmOut(user=me_out(build_context(db, user, new.id, now)), backup_codes=codes)


@router.post("/logout", status_code=204)
def logout(
    db: DB,
    meta: Meta,
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> Response:
    """M11: sessiya bo'lmasa/yaroqsiz bo'lsa ham har doim 204 — faqat cookie'larni tozalaydi.

    Sessiya haqiqiy bo'lsa, CSRF tekshiruvi baribir talab qilinadi (aks holda uchinchi
    tomon saytdan chaqirilgan so'rov boshqa foydalanuvchining sessiyasini bekor qilardi).
    """
    now = datetime.now(UTC)
    if session_cookie:
        resolved = sessions.resolve(db, session_cookie, now)
        if resolved is not None:
            sess, user = resolved
            if not csrf_ok(session_cookie, csrf_cookie, csrf_header):
                raise ForbiddenError("csrf_failed")
            service.logout(db, sess.id, user.id, meta, now)
    response = Response(status_code=204)
    _clear_cookies(response)
    return response


@router.get("/me")
def me(ctx: Ctx) -> MeOut:
    return me_out(ctx)


@router.post("/password/change", status_code=204)
def change_password(body: PasswordChangeIn, ctx: Ctx, db: DB, meta: Meta) -> Response:
    new = service.change_password(
        db, ctx, body.current_password, body.new_password, meta, datetime.now(UTC)
    )
    response = Response(status_code=204)
    _set_session_cookies(response, new)  # M8: sessiya aylantiriladi — yangi cookie'lar
    return response


@router.get("/sessions")
def list_sessions(ctx: Ctx, db: DB) -> list[SessionOut]:
    return service.list_sessions(db, ctx, datetime.now(UTC))


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: uuid.UUID, ctx: Ctx, db: DB, meta: Meta) -> Response:
    service.revoke_own_session(db, ctx, session_id, meta, datetime.now(UTC))
    return Response(status_code=204)
