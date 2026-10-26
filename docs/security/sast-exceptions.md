# Реестр исключений статического анализа

Любое подавление срабатывания анализатора (`# nosec`, `# noqa: S…`, `# nosemgrep`, allowlist gitleaks,
`.trivyignore`, `ignored` в `.hadolint.yaml`) допускается только с записью в этой таблице.
Реестр пересматривается при каждом релизе (`docs/ops/install-upgrade.md`, раздел «Выпуск релиза»).

| Инструмент | Правило | Место | Обоснование | Добавлено |
|---|---|---|---|---|
| bandit | B108 (временный каталог) | `backend/app/worker.py` (`HEARTBEAT`) | Файл-отметка для healthcheck в tmpfs контейнера (`/tmp`), данных не содержит, каталог недоступен другим пользователям | 2026-09-25 |
| ruff | S608 (SQL из строк) | `backend/app/core/reencrypt.py`, `backend/app/audit/router.py`, `backend/app/etl/merge.py`, `backend/app/dwh/`, `backend/app/admin/config_service.py`, `backend/app/admin/etl_router.py`, `backend/migrations/versions/` | Имена таблиц и столбцов берутся только из реестров в коде (whitelist), значения передаются параметрами | 2026-09-25 |
| ruff | S311 (псевдослучайный генератор) | `backend/app/etl/synthetic/` | Детерминированный генератор синтетических данных, не используется для секретов | 2026-09-25 |
| ruff | S105 (строка похожа на пароль) | `backend/app/audit/service.py` (`AuditAction`) | Коды событий аудита (`auth.password.ok` и т. п.), не пароли | 2026-09-25 |
| ruff | S105 (строка похожа на пароль) | `backend/app/devtools.py` (`E2E_PASSWORD`, `E2E_TOTP_SECRET`) | Открытые значения E2E; `seed-e2e`/`seed-load` отказывают вне явного `ENV=dev`/`test` | 2026-10-26 |
| ruff | S105, S106, S108, S311, S603, S607, S608 | `backend/tests/` (per-file-ignores в `backend/pyproject.toml`) | Тестовые значения, фиксированные пути и запуск скриптов репозитория в тестах; в образ не входят (`backend/.dockerignore`) | 2026-10-26 |
