"""Xatolar daraxti va yagona javob formati: {"error": {code, message, request_id, params?}}.

Ichki tafsilotlar (stack trace, SQL, kiritilgan qiymatlar) hech qachon javobga chiqmaydi.
`AppError`ning `**params`i mijozga aynan shu ko'rinishda qaytariladi — ularga hech qachon
sezgir qiymatlar (parol, token va h.k.) uzatilmasin.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger("ugekazna.errors")

MESSAGES: dict[str, str] = {
    "bad_request": "Некорректный запрос",
    "unauthenticated": "Требуется вход в систему",
    "session_expired": "Сеанс завершён, войдите снова",
    "invalid_credentials": "Неверный логин или пароль",
    "invalid_mfa_code": "Неверный код подтверждения",
    "mfa_expired": "Время подтверждения истекло, войдите снова",
    "mfa_already_enabled": "Двухфакторная аутентификация уже подключена",
    "forbidden": "Недостаточно прав",
    "csrf_failed": "Запрос отклонён: проверка CSRF не пройдена",
    "password_change_required": "Необходимо сменить пароль",
    "scope_violation": "Нет доступа к данным этого филиала",
    "not_found": "Не найдено",
    "conflict": "Конфликт данных",
    "conflict_modified": "Запись изменена другим пользователем, обновите страницу",
    "username_taken": "Логин уже занят",
    "code_taken": "Код уже используется",
    "last_admin": "Нельзя оставить систему без администратора",
    "admin_role_protected": "У роли администратора нельзя отнять права администрирования",
    "cannot_modify_self": "Это действие нельзя выполнить со своей учётной записью",
    "privilege_escalation": "Нельзя выдать права, которых нет у вас",
    "validation_failed": "Проверьте введённые данные",
    "invalid_current_password": "Текущий пароль указан неверно",
    "password_policy": "Пароль не соответствует политике",
    "unknown_permission": "Неизвестное право доступа",
    "rate_limited": "Слишком много запросов, повторите позже",
    "payload_too_large": "Слишком большой запрос",
    "method_not_allowed": "Метод не поддерживается",
    "build_not_available": "Сборка недоступна",
    "unknown_source": "Неизвестный источник данных",
    "source_forbidden": "Источник недоступен в этой среде",
    "invalid_setting": "Недопустимое значение настройки",
    "internal_error": "Внутренняя ошибка сервера",
}


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        code: str | None = None,
        *,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
        **params: Any,
    ) -> None:
        self.code = code or type(self).code
        if status_code is not None:
            self.status_code = status_code
        self.headers = headers or {}
        self.params = params
        super().__init__(self.code)


class AuthError(AppError):
    status_code = 401
    code = "unauthenticated"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class PasswordChangeRequired(ForbiddenError):  # noqa: N818 -- nom brief'da shartlangan
    code = "password_change_required"


class ScopeViolationError(ForbiddenError):
    code = "scope_violation"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailed(AppError):  # noqa: N818 -- nom brief'da shartlangan
    status_code = 422
    code = "validation_failed"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, retry_after: int) -> None:
        super().__init__(headers={"Retry-After": str(retry_after)}, retry_after=retry_after)


def _payload(request: Request, code: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": code,
        "message": MESSAGES.get(code, MESSAGES["bad_request"]),
        "request_id": getattr(request.state, "request_id", None),
    }
    if params:
        body["params"] = params
    return {"error": body}


def error_response(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        _payload(request, exc.code, exc.params), status_code=exc.status_code, headers=exc.headers
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(request, exc)

    @app.exception_handler(ScopeViolationError)
    async def _scope_violation(request: Request, exc: ScopeViolationError) -> JSONResponse:
        from app.audit.service import AuditAction, log_event
        from app.core.request_meta import client_meta

        ctx = getattr(request.state, "auth", None)
        await run_in_threadpool(
            log_event,
            client_meta(request),
            AuditAction.RLS_VIOLATION,
            user_id=getattr(ctx, "user_id", None),
            result="denied",
            details={"path": request.url.path, **exc.params},
        )
        return error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        skip = {"body", "query", "path", "header", "cookie"}
        fields = sorted(
            {".".join(str(p) for p in e.get("loc", ()) if p not in skip) for e in exc.errors()}
        )
        return JSONResponse(
            _payload(request, "validation_failed", {"fields": fields}), status_code=422
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}.get(
            exc.status_code, "bad_request"
        )
        return JSONResponse(_payload(request, code), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", path=request.url.path, error_type=type(exc).__name__,
                  exc_info=exc)
        return JSONResponse(_payload(request, "internal_error"), status_code=500)
