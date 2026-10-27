# Контрольный список безопасной конфигурации

Список проверяется при вводе в эксплуатацию и при каждом релизе. Автоматические проверки указаны в
колонке «Как проверить». Раздел 1 описывает требования к хосту: они выполняются при установке по
[../ops/host-hardening.md](../ops/host-hardening.md) и проверяются вручную при приёмке, автоматических
тестов репозитория для них нет.

## 1. Сервер

| Требование | Как проверить |
|---|---|
| Диски данных и копий зашифрованы LUKS2 (aes-xts-plain64, 512 бит) | `cryptsetup luksDump <устройство>` |
| Администраторы ОС — только группа `ugk-admins`; членство в группе `docker` эквивалентно root | `getent group ugk-admins docker` |
| SSH только по ключам, без root, только из VPN | `sshd -T \| grep -E 'passwordauthentication\|permitrootlogin'` |
| Межсетевой экран: 443/80 и SSH только из подсетей VPN, правила DOCKER-USER | `ufw status verbose`, `iptables -L DOCKER-USER` |
| chrony синхронизирован (`System time` не более 0,1 с) | `chronyc tracking` |
| auditd с правилами UGEKAZNA | `auditctl -l \| grep ugk` |
| Автоматические обновления безопасности | `systemctl status unattended-upgrades` |

Подробно — [../ops/host-hardening.md](../ops/host-hardening.md).

## 2. Docker

| Требование | Как проверить |
|---|---|
| `userns-remap`, `live-restore`, `no-new-privileges`, ограничение журналов, `icc: false` | `docker info`, `/etc/docker/daemon.json` |
| Каждый сервис: read-only, `cap_drop: ALL`, `no-new-privileges`, non-root, лимиты памяти/CPU/процессов, ротация журналов | `test_every_service_is_hardened` |
| Healthcheck у всех сервисов, кроме одноразового `migrate` | `test_healthchecks` |
| Только Caddy публикует порты (8443/8080 → 443/80) | `test_only_caddy_publishes_unprivileged_ports` |
| Сети `backend` и `web` внутренние; из внутренних сетей выход наружу только у worker (сеть `egress`), caddy — в сети `edge` для публикации портов; `backup` без сети | `test_network_isolation` |
| Секреты не в переменных окружения | `test_no_secrets_in_environment` |
| Образы — только релизные теги, базовые образы по digest | `test_images_are_own_versioned_images`, `test_base_images_pinned_by_digest` |

## 3. Приложение

| Требование | Как проверить |
|---|---|
| `ENV=prod` для api, worker, migrate | `test_backend_services_run_in_prod_mode` |
| Приложение не стартует с тестовыми ключами, HTTP-адресом, быстрым профилем Argon2, пустым паролем Redis | `test_prod_rejects_test_keys_http_and_fast_hash` |
| uvicorn: 4 процесса, без `--reload`; `--no-server-header`; `X-Forwarded-For` только из подсети `web` | `test_api_runs_four_uvicorn_workers`, `test_api_trusts_forwarded_only_from_web_subnet` |
| OpenAPI в prod только с разрешением `admin:settings` | `backend/app/main.py` |
| Команды разработки (`seed-e2e`, `seed-load`) отказывают вне dev/test (`ALLOWED_ENVS` в `backend/app/devtools.py`) | `test_seed_load_refuses_outside_dev_and_test` |

## 4. PostgreSQL

| Требование | Как проверить |
|---|---|
| `password_encryption = scram-sha-256`; `pg_hba`: суперпользователь только локально, приложения только `samenet` | `test_pg_hba_only_scram_and_reject` |
| `pg_stat_statements`, `auto_explain`, журнал медленных запросов 500 мс | `test_postgresql_conf_security_settings`, `make db-smoke` |
| Контрольные суммы страниц (`--data-checksums`) при инициализации | `docker compose … exec db psql -U postgres -tAc 'SHOW data_checksums'` → `on` |
| Пароли ролей не попадают в журнал | `test_initdb_roles_do_not_log_passwords` |
| Роли без `BYPASSRLS`, RLS принудительный | `test_app_role_has_no_bypassrls`, `test_all_facts_exist_with_forced_rls` |

## 5. Redis

| Требование | Как проверить |
|---|---|
| Пароль, ACL без опасных команд, без сохранения на диск, `maxmemory 256mb` | `deploy/compose.prod.yml` (сервис `redis`) |
| Только внутренняя сеть | `test_network_isolation` |

## 6. Caddy

| Требование | Как проверить |
|---|---|
| TLS 1.2/1.3, ECDHE + AEAD, корпоративный сертификат, без ACME, `admin off` | `test_caddy_prod_basics`, `test_tls_only_modern_protocols`, `make test-caddy` |
| Заголовки безопасности совпадают с приложением | `test_security_headers_match_backend` |
| `/api/v1/healthz`, `/api/v1/readyz` снаружи — 404; тело ≤ 1 МБ | `test_probes_blocked_before_api_proxy`, `make test-caddy` |

## 7. Секреты и ключи

| Требование | Как проверить |
|---|---|
| Файлы секретов `root:<группа> 0440`, каталог `0750` | `scripts/secrets_perms.sh`, `stat -c '%U:%G %a' <файл>` |
| Копии KEK и пароля репозитория в сейфе | журнал сейфа ([key-management.md](key-management.md), П2) |
| Нет секретов в репозитории | `make check` (gitleaks) |

## 8. Резервное копирование

| Требование | Как проверить |
|---|---|
| Шифрование репозитория, отдельный диск | `test_pgbackrest_conf_encrypted_without_password`, `docker volume inspect ugk_pgbackrest_repo` |
| Копии свежие и без ошибок | healthcheck сервиса `backup`, `make backup-status` |
| Ежемесячная проверка восстановления выполнена успешно | `make backup-status` (`last_restore_test`), `ops-check` |

## 9. CI

| Требование | Как проверить |
|---|---|
| `make check`, `make e2e-ci` и `make scan` обязательны для слияния | `.gitlab-ci.yml`, `.github/workflows/ci.yml`, `test_github_runs_same_make_targets` |
| Pre-commit подключён у разработчиков | `git config core.hooksPath` → `.githooks` |
| Исключения анализаторов обоснованы | [sast-exceptions.md](sast-exceptions.md) |

## 9a. Настройки, управляемые из панели администратора

Значения политики хранятся в `core.settings` (версии, журнал аудита) и меняются в разделах
«Настройки», «Политика безопасности», «Интеграции» без перезапуска (до 30 секунд для других процессов,
расписания — до 60 секунд). Инфраструктура (ключи, пароли ролей СУБД, TLS, порты, сети, `ENV`) в панель
не выводится и меняется только оператором ОС.

| Настройка | По умолчанию | Допустимо | Кто меняет |
|---|---|---|---|
| Завершение сеанса при бездействии | 30 мин | 5–30 | `admin:security` |
| Максимальная длительность сеанса | 12 ч | 1–12 | `admin:security` |
| Срок действия пароля | 90 дн. | 30–90 | `admin:security` |
| Попыток входа до блокировки / блокировка | 5 / 15 мин | 3–5 / 15–1440 мин | `admin:security` |
| Минимальная длина пароля / история | 12 / 5 | 12–64 / 5–24 | `admin:security` |
| Попыток входа и 2FA с IP в минуту, запросов API пользователя | 10, 20, 300 | не выше значений по умолчанию | `admin:security` |
| Хранение журнала аудита / фактов | 12 мес. / 5 лет | ≥ 12 мес. / ≥ 5 лет | `admin:security` / `admin:settings` |
| Проверка восстановления не реже, чем раз в | 40 дн. | 1–40 | `admin:security` |

Ослабить политику относительно значений по умолчанию нельзя: граница проверяется при записи и при
чтении — недопустимое значение в базе игнорируется (`test_security_bounds_are_tighten_only`,
`test_invalid_panel_value_falls_back`, `test_weaker_panel_value_is_ignored`). Изменение настроек
безопасности и интеграций требует причины и текущего кода 2FA, повтор кода отклоняется
(`test_guarded_key_needs_reason_and_fresh_totp`, `test_step_up_rejects_replayed_code`); в лимит
попыток подтверждения (5 за 15 минут) входят только неверные коды
(`test_step_up_rate_limit_counts_only_failures`), резервный код не принимается
(`test_step_up_rejects_backup_code`).
Учётные данные интеграций хранятся зашифрованными (AES-256-GCM, назначение `integration_creds`), API
их не возвращает; смена адреса или порта сервера удаляет сохранённый пароль
(`test_secret_is_encrypted_and_never_returned_or_audited`, `test_endpoint_change_clears_panel_secret`,
`test_env_secret_not_used_once_endpoint_is_set_in_panel`).

Известные особенности (приняты):

- Уже выданные сеансы не укорачиваются при ужесточении лимитов: новые пределы действуют для новых и
  продлеваемых сеансов (до прежних 30 минут бездействия / 12 часов).
- «Проверить подключение» к SMTP позволяет администратору с `admin:integrations` и свежим кодом 2FA
  различать закрытые и открытые порты внутренних адресов (коды `connect_failed`, `timeout`,
  `protocol_error`); каждая смена адреса — событие аудита, активна не более одной проверки на
  интеграцию.
- При недоступной базе данных письма (в том числе «база недоступна» от `ops-check`) отправляются с
  параметрами SMTP из конфигурации сервера (`test_smtp_config_falls_back_to_env_when_db_is_down`):
  пароль из env используется только вместе с адресом из env.
- Роль `ugk_etl` имеет право чтения таблицы `core.integration_credentials` (нужно для подключения 1С);
  сейчас её использует только `ugk_app`. Сужение (представление или RLS по имени) — при подключении 1С.

## 10. Правила разработки

1. Эндпоинт данных обязан зависеть от `Ctx` (`get_ctx`): только так в транзакции устанавливается
   контекст RLS (`apply_rls`); без него запросы к `pub.*` возвращают 0 строк; другой scope
   `Depends(get_db)` запрещён (`test_get_db_only_via_db_alias`).
2. Данные разделов читаются только из представлений `pub.*` (не из `dwh`/`mart` напрямую) —
   шаблон `docs/dev/section-endpoint-pattern.md`.
3. Каждая миграция, создающая таблицу, явно выдаёт `GRANT` нужным ролям (`ALTER DEFAULT PRIVILEGES`
   не используется) и включает `ENABLE` + `FORCE ROW LEVEL SECURITY` для таблиц со столбцом `branch_id`.
4. SQL — только с параметрами; имена таблиц и столбцов — только из реестров кода.
5. Новое чувствительное поле: столбец `*_enc`, регистрация в `REGISTRY` (`backend/app/core/reencrypt.py`),
   AAD `{схема}.{таблица}.{столбец}:{ключ}`, при поиске — blind index.
6. Метки HMAC (`keyed_hash`, `blind_index`) — константы кода без символа `|`.
7. Изменения прав, настроек, ключей, выгрузки — обязательно событие аудита.
8. Новые ключи журналов с чувствительными значениями добавляются в маскирование
   (`backend/app/core/logging.py`).
9. Подавление анализаторов (`# nosec`, `# nosemgrep`, `.trivyignore`, allowlist gitleaks) — только с
   записью в [sast-exceptions.md](sast-exceptions.md).
10. Зависимости — через `make lock` (хеши). Заголовок lock-файла показывает `--no-index` — особенность
    pip-tools 7.6.1, на установку не влияет.
11. Фронтенд: без inline-стилей и скриптов, без `dangerouslySetInnerHTML`, без CDN.
12. Миграции содержат `downgrade`, но деструктивные откаты (0001 — схемы, 0002 — ключи шифрования,
    0004 — журнал аудита) в prod не выполняются никогда ([../ops/install-upgrade.md](../ops/install-upgrade.md)).
13. Перед релизом: `make check`, `make scan`, `make backup-selftest`, `make e2e` (в CI — `make e2e-ci`), нагрузочный тест на
    тестовом контуре; изменение архитектуры — вместе с изменением [threat-model.md](threat-model.md).
14. Новая настройка — только запись `SettingDef` в `backend/app/core/sysconfig.py` (тип, границы,
    раздел, разрешение); новый секрет внешней системы — `SecretDef` в `backend/app/core/integrations.py`.
    Константы политики в коде и новые переменные окружения для неё не добавляются.

## 11. Устранение замечаний Центра кибербезопасности (письмо 05-29-02/5323 от 22.09.2026)

Замечания (резолюция № 09-1699) относились к ранее эксплуатировавшейся системе: A01 — принудительный
просмотр (force browsing) каталога `/.git`, A02 — учётные данные, зашитые в код. Ниже указано, как
UGEKAZNA исключает их по конструкции, и чем это подтверждается.

### A01. Принудительный просмотр `/.git` и служебных файлов

| Мера | Реализация | Проверка |
|---|---|---|
| В образ веб-сервера попадает только собранная статика | `frontend/Dockerfile`: этап `web` копирует в `/srv` только `/app/dist` (результат `npm run build`); Caddy отдаёт только `/srv`. Исходники, `.git`, `.env` в образе отсутствуют | Проверка содержимого образа: `scripts/tests/caddy_prod_test.sh` (`find` по образу на `.git`, `*.map`, `src`); `deploy/tests/probe_caddy.py` (`make test-caddy`) запрашивает `/.git/config`, `/.git/HEAD`, `/.env`, `/deploy/compose.prod.yml`, `/backend/app/core/config.py`, `/src/main.tsx`: ответ только 403/404 и не страница SPA |
| Образ API содержит только код приложения | `backend/Dockerfile` копирует `app/`, `migrations/`, `alembic.ini`, `pyproject.toml`; `backend/.dockerignore` исключает `tests`, `tools` | — |
| Исходный код не монтируется в prod-контейнеры | `deploy/compose.prod.yml`: только именованные тома | `test_no_source_bind_mounts` |
| Образы релиза собираются из `git archive HEAD`, а не из рабочего каталога | `scripts/release.sh` | `test_release_builds_from_clean_export` |
| Любой путь с сегментом, начинающимся с точки (`.git`, `.env`, `.DS_Store`), — 404 до SPA-страницы и до прокси API; учитываются `%2e`, `..`, обратная косая черта; исключение — `/.well-known/<имя>` без точек | `deploy/caddy/Caddyfile.prod`, матчер `@dotseg` (то же в `Caddyfile.dev`) | `test_dotfile_matcher_before_spa_in_dev_and_prod`; поведение — `deploy/tests/probe_caddy.py` (`force_browse`, в том числе `/%2e%2e/etc/passwd`, `/%5c.git/config`, `/.well-known/.git/config`) |
| Путь с расширением, которого нет в сборке, — 404, а не `index.html` | `Caddyfile.prod`, матчер `@spa` | `deploy/tests/probe_caddy.py` |
| Листинга каталогов нет; запрос к серверу по IP или с чужим Host — 421 | `Caddyfile.prod` (`file_server` без `browse`, блок `https://`) | `test_unknown_host_and_no_sni_hardened` |

Ограничение: поведенческая проверка `make test-caddy` запускается отдельно (перед выпуском релиза) и
в `make check` не входит; статический тест `test_dotfile_matcher_before_spa_in_dev_and_prod` входит в
каждый прогон `pytest`.

### A02. Учётные данные в коде

| Мера | Реализация | Проверка |
|---|---|---|
| Поиск секретов во всей истории репозитория | `make check` → `scripts/check_repo.sh` → gitleaks в режиме `git` по всем коммитам (`deploy/compose.tools.yml`); CI клонирует полную историю (`fetch-depth: 0`) | `scripts/tests/gitleaks_selftest.sh` (реальный токен находится, открытые тестовые значения — нет) |
| Поиск секретов до коммита | `.githooks/pre-commit` → gitleaks по staged-изменениям (`make hooks`) | `scripts/tests/hook_selftest.sh` |
| Исключения gitleaks — только точные значения, перечисленные в реестре | `.gitleaks.toml`, [sast-exceptions.md](sast-exceptions.md) | `scripts/tests/gitleaks_selftest.sh` |
| Нет учётной записи по умолчанию | Миграции не создают пользователей; первого администратора создаёт оператор командой `create-admin` (`backend/app/cli.py`): индивидуальный логин, временный пароль из CSPRNG показывается один раз, смена пароля и подключение TOTP-2FA обязательны при первом входе | `test_cli_create_admin_and_audit_verify`, `test_create_user_and_first_login_requires_enroll` |
| Пароли пользователей не хранятся в открытом виде | Argon2id (64 МиБ, 3 итерации, параллелизм 4), уникальная соль | `test_standard_params_match_spec`, `test_hash_and_verify` |
| Секреты не в коде, образах и переменных окружения | Docker secrets; `scripts/gen_secrets.py` создаёт случайные значения (256 бит); файлы `0440`, каталог `0750` (`scripts/secrets_perms.sh`) | `test_generates_all_secrets_once`, `test_no_secrets_in_environment`, `test_secrets_are_scoped`, `test_dockerignore_excludes_secrets` (контекст сборки образа СУБД не содержит `deploy/secrets`) |
| Приложение не запускается в prod с тестовыми ключами | `Settings.problems()`, `ENV` по умолчанию — prod | `test_prod_rejects_test_keys_http_and_fast_hash`, `test_env_defaults_to_prod_when_unset` |
| Учётные данные внешних систем (1С, банки) не хранятся в коде или конфигурации | Хранение в зашифрованном виде (AES-256-GCM, ключ `integration_creds`) реализуется в плане 04b; в текущей версии таких данных в системе нет | — |

Открытые значения, которые есть в репозитории, и их границы. Пароль и TOTP-секрет E2E-пользователей
(`E2E_PASSWORD`, `E2E_TOTP_SECRET` в `backend/app/devtools.py`) и тестовые ключи
(`TEST_KEYS` в `backend/app/core/config.py`, `deploy/compose.test.yml`) предназначены только для
контуров dev и test: команды `seed-e2e` и `seed-load` отказывают вне `ENV=dev`/`test`, приложение с
тестовыми ключами в prod не запускается, остаточные нагрузочные учётные записи `load_*` в prod
обнаруживает `ops-check` (`load_users_present`). Эти значения внесены в реестр
[sast-exceptions.md](sast-exceptions.md).
