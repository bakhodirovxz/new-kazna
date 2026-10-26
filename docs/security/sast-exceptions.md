# Реестр исключений статического анализа

Любое подавление срабатывания анализатора (`# nosec`, `# noqa: S…`, `# nosemgrep`, allowlist gitleaks,
`.trivyignore`, `ignored` в `.hadolint.yaml`) допускается только с записью в этой таблице.
Реестр пересматривается при каждом релизе (`docs/ops/install-upgrade.md`, раздел «Выпуск релиза»).

| Инструмент | Правило | Место | Обоснование | Добавлено |
|---|---|---|---|---|
| bandit B108 / ruff S108 | временный каталог | `backend/app/worker.py` (`HEARTBEAT`) | Файл-отметка для healthcheck в tmpfs контейнера (`/tmp`), данных не содержит, каталог недоступен другим пользователям | 2026-09-25 |
| ruff | S608 (SQL из строк) | `backend/app/core/reencrypt.py`, `backend/app/audit/router.py`, `backend/app/etl/merge.py`, `backend/app/dwh/`, `backend/app/admin/config_service.py`, `backend/app/admin/etl_router.py`, `backend/migrations/versions/` | Имена таблиц и столбцов берутся только из реестров в коде (whitelist), значения передаются параметрами | 2026-09-25 |
| ruff | S311 (псевдослучайный генератор) | `backend/app/etl/synthetic/` | Детерминированный генератор синтетических данных, не используется для секретов | 2026-09-25 |
| ruff | S105 (строка похожа на пароль) | `backend/app/audit/service.py` (`AuditAction`) | Коды событий аудита (`auth.password.ok` и т. п.), не пароли | 2026-09-25 |
| ruff | S105 (строка похожа на пароль) | `backend/app/devtools.py` (`E2E_PASSWORD`, `E2E_TOTP_SECRET`) | Открытые значения E2E; `seed-e2e`/`seed-load` отказывают вне явного `ENV=dev`/`test` | 2026-10-26 |
| ruff | S105, S106, S108, S311, S603, S607, S608 | `backend/tests/` (per-file-ignores в `backend/pyproject.toml`) | Тестовые значения, фиксированные пути и запуск скриптов репозитория в тестах; в образ не входят (`backend/.dockerignore`) | 2026-10-26 |
| ruff | S101 (assert) | `backend/pyproject.toml` (глобальный ignore) | `assert` только для сужения типов в mypy (`backend/app/auth/service.py:229`, `backend/app/etl/merge.py:426`), не для проверок доступа; bandit B101 ниже порога `-ll` | 2026-10-26 |
| gitleaks | allowlist (значение) | `backend/app/core/config.py` (`TEST_KEYS`), `deploy/compose.test.yml` | Открытые тестовые ключи; в `ENV=prod` приложение с ними не запускается (`Settings.problems()`) | 2026-09-25 |
| gitleaks | allowlist (значение) | `backend/app/devtools.py`, `frontend/e2e/fixtures.ts` | Пароль и TOTP-секрет E2E (пример из RFC 6238); команда `seed-e2e` отказывает вне `dev`/`test` | 2026-09-25 |
| gitleaks | allowlist (значение) | `deploy/compose.test.yml` | Пароли одноразового тестового стенда (`test-app` и т. п.) | 2026-09-25 |
| hadolint | DL3018 (версии apk) | все Dockerfile (глобально, `.hadolint.yaml`) | Базовый образ закреплён по digest (`deploy/images.lock.env`); репозиторий релиза Alpine выдаёт только исправления безопасности | 2026-09-25 |
| gitleaks | allowlist (значение) | `frontend/e2e/specs/totp.spec.ts`, `frontend/src/admin/users.test.tsx`, `frontend/src/auth/auth.test.tsx`, `frontend/e2e/fixtures.ts`, `docs/superpowers/plans/2026-09-24-03-frontend.md` | Тестовый вектор RFC 6238 и вымышленные пароли из модульных тестов и E2E | 2026-10-26 |
| semgrep | `# nosemgrep: avoid-sqlalchemy-text` (`python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text`) | 22 вызова `text(f"…")`/`text(<константа>)` в `backend/app/admin/config_service.py`, `backend/app/admin/etl_router.py`, `backend/app/audit/router.py`, `backend/app/audit/service.py`, `backend/app/core/keystore.py`, `backend/app/core/reencrypt.py`, `backend/app/dwh/aggregates.py`, `backend/app/dwh/builds.py`, `backend/app/etl/merge.py` | В SQL подставляются только идентификаторы и фрагменты из реестров и констант в коде (whitelist); значения всегда передаются связанными параметрами. Построчные комментарии; глобального исключения правила нет (новое использование `text(f"…")` будет найдено) | 2026-10-26 |
| hadolint | DL3006 (тег базового образа) | `backend/Dockerfile`, `frontend/Dockerfile`, `deploy/postgres/Dockerfile` | Базовый образ задаётся `ARG` (тег по умолчанию для dev); в prod передаётся digest из `deploy/images.lock.env` | 2026-10-26 |
