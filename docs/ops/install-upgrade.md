# Установка, обновление и откат

## 1. Пакет релиза

Выпускается командой `make release VERSION=<версия>` на сборочной машине (рабочий каталог без
незакоммиченных изменений; образы собираются из `git archive HEAD`, `make scan` выполняется внутри
`scripts/release.sh`) и содержит: `images/ugekazna-images-<версия>.tar` (образы `ugekazna-db`, `ugekazna-redis`,
`ugekazna-backend`, `ugekazna-web`), `sbom/`, `deploy/` (конфигурация, `release.env` с `UGK_VERSION`),
`scripts/`, `docs/security/`, `docs/ops/`, `Makefile`, `COMMIT`, `SHA256SUMS`. Базовые образы
закреплены по digest (`deploy/images.lock.env`); перед выпуском выполняются `make check`,
`make backup-selftest`, E2E и нагрузочный тест на тестовом контуре.

Сборка не побитово воспроизводима: при сборке образов выполняются `apt-get upgrade` и `apk upgrade`
(исправления безопасности после даты базового образа), поэтому состав образа зависит от даты сборки.
Документом учёта является сам пакет релиза: образы в `images/`, SBOM в `sbom/` и `SHA256SUMS`;
повторная сборка того же коммита позже даст другой состав.

## 2. Первичная установка

Условия: сервер подготовлен по [host-hardening.md](host-hardening.md); получены корпоративный
сертификат (PEM с цепочкой) и ключ; выбран профиль (`8gb` или `16gb`).

1. Проверка и распаковка пакета:
   ```bash
   mkdir -p /opt/ugekazna/releases /opt/ugekazna/shared /var/log/ugekazna
   tar -xzf ugekazna-1.0.0.tar.gz -C /opt/ugekazna/releases
   cd /opt/ugekazna/releases/ugekazna-1.0.0 && sha256sum -c SHA256SUMS
   docker load -i images/ugekazna-images-1.0.0.tar
   ```
2. Параметры площадки: `cp deploy/prod.env.example /opt/ugekazna/shared/prod.env`, заполнить
   `UGK_DOMAIN`, `UGK_BIND_ADDR`, профиль (`UGK_PG_PROFILE`, `UGK_DB_MEM`, `UGK_DB_CPUS`),
   `UGK_WEB_SUBNET` (если подсеть `172.31.250.0/24` занята), `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`,
   `SMTP_TO`, `SMTP_USER`, `SMTP_STARTTLS`, `SMTP_SSL`; `chmod 0640 /opt/ugekazna/shared/prod.env`.
   Сертификат SMTP-релея проверяется по системным центрам сертификации образа; в образ приложения
   корпоративный CA по умолчанию не входит (`RUNTIME_EXTRA_CA=false`), поэтому релей с сертификатом
   корпоративного УЦ потребует сборки образа с `--build-arg RUNTIME_EXTRA_CA=true` (`backend/certs/README.md`).
   Пароль SMTP передаётся только по защищённому соединению (STARTTLS или SSL), иначе приложение не
   запустится; значение пароля записывается в файл секрета `smtp_password`, а не в `prod.env`.
   Сервис `worker` — строго один экземпляр (не масштабировать `--scale worker=N`): восстановление
   зависших запросов загрузки при старте рассчитано на один процесс.
3. Секреты ([../security/key-management.md](../security/key-management.md), П1 и П2):
   ```bash
   python3 scripts/gen_secrets.py /opt/ugekazna/shared/secrets
   install -m 0400 <сертификат>.pem /opt/ugekazna/shared/secrets/tls_cert.pem
   install -m 0400 <ключ>.pem /opt/ugekazna/shared/secrets/tls_key.pem
   scripts/secrets_perms.sh /opt/ugekazna/shared/secrets
   ```
   Сразу выполнить резервное копирование секретов в сейф (П2). Если SMTP-релей требует пароль,
   записать его в `/opt/ugekazna/shared/secrets/smtp_password` до запуска `secrets_perms.sh`.
4. Том репозитория копий на отдельном диске:
   ```bash
   # userns-remap: uid/gid = база dockremap из /etc/subgid + 70 (как в scripts/secrets_perms.sh)
   BASE="$(awk -F: '$1 == "dockremap" { print $2; exit }' /etc/subgid)"   # без userns-remap: BASE=0
   install -d -m 0750 -o $((BASE + 70)) -g $((BASE + 70)) /srv/ugk-backup/repo
   docker volume create --driver local --opt type=none --opt o=bind \
     --opt device=/srv/ugk-backup/repo ugk_pgbackrest_repo
   ```
5. Активация релиза:
   ```bash
   ln -sfn /opt/ugekazna/releases/ugekazna-1.0.0 /opt/ugekazna/current
   cd /opt/ugekazna/current && ln -sfn /opt/ugekazna/shared/prod.env deploy/prod.env
   $P up -d
   $P ps
   ```
   Миграции выполняет одноразовый сервис `migrate` до запуска `api` и `worker`. На сервере не должно
   быть dev-стенда с тем же именем проекта `ugekazna` ([README.md](README.md)).
6. Первый администратор: `make create-admin u=<логин> n="<ФИО>" STACK=prod`
   (или `$P exec -T api python -m app.cli create-admin --username <логин> --full-name "<ФИО>"`)
   — временный пароль выводится один раз; далее — [admin-guide.md](admin-guide.md), раздел 2.
7. Проверки: `https://<домен>/` открывает страницу входа; `curl -s -o /dev/null -w '%{http_code}' https://<домен>/api/v1/healthz`
   → `404` (служебный путь закрыт); `http://<домен>/` → 308 на HTTPS; после завершения первой полной копии
   (`UGK_BACKUP_INITIAL_FULL=yes`) сервис `backup` в состоянии `healthy`.
8. Таймеры мониторинга и проверки восстановления:
   ```bash
   cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now ugekazna-monitor.timer ugekazna-restore-test.timer
   ```
   Требуются systemd не ниже 235 и настроенная пересылка журналов в SIEM
   ([host-hardening.md](host-hardening.md), раздел 9).
9. Первая проверка восстановления вручную: `UGK_LOG_DIR=/var/log/ugekazna scripts/restore_test.sh`
   ([backup-restore.md](backup-restore.md)).

## 3. Обновление

Выполняется вне рабочего времени с предупреждением пользователей.

1. Проверить и загрузить новый пакет (шаг 1 раздела 2).
2. Внеочередная копия перед миграциями: `$P exec -T backup ugk-backup once full`; сохранить метку
   (`$P exec -T backup ugk-backup latest`) и время начала обновления.
3. Переключить релиз и запустить:
   ```bash
   ln -sfn /opt/ugekazna/releases/ugekazna-1.1.0 /opt/ugekazna/current
   cd /opt/ugekazna/current && ln -sfn /opt/ugekazna/shared/prod.env deploy/prod.env
   $P up -d
   ```
4. Проверки: `$P ps -a` (все сервисы `healthy`, `migrate` — `exited (0)`), вход, `make ops-check STACK=prod`,
   `make audit-verify STACK=prod`.

## 4. Откат

- **Ошибка миграции** (`migrate` завершился с ошибкой): каждая ревизия Alembic выполняется в
  отдельной транзакции (`transaction_per_migration`), поэтому при сбое схема остаётся на последней
  успешно применённой ревизии, а не на исходной. Сервисы `api`, `worker` и `caddy` зависят от
  `migrate` и новым релизом не запускаются; прежние `api` и `worker` при этом продолжают работать
  с частично изменённой схемой — до решения откатом или новым релизом ограничьте доступ. Определить ревизию:
  `$P run --rm -T migrate alembic current`. Если применены не все ревизии релиза — это изменение
  схемы, см. ниже; если ни одна — вернуть ссылку `current` на прежний релиз и выполнить `$P up -d`.
- **Проблема после успешного обновления без изменения схемы**: вернуть ссылку `current` и `$P up -d`.
- **Проблема после изменения схемы**: предпочтительно исправление новым релизом. Если нужен возврат —
  (а) `$P run --rm -T migrate alembic downgrade <ревизия>` только если в примечаниях к релизу откат
  отмечен как безопасный; иначе (б) восстановление на момент перед обновлением
  ([backup-restore.md](backup-restore.md), раздел 5, `--type=time`, время из шага 2) и прежний релиз.
  Данные, введённые после обновления, при варианте (б) теряются — решение принимает владелец системы.

**Политика отката миграций.** Откат ревизий `0001` (удаляет схемы), `0002` (удаляет таблицу ключей
шифрования — все зашифрованные данные становятся невосстановимыми) и `0004` (удаляет журнал аудита и
его цепочку — уничтожает доказательства) в prod **не выполняется никогда**; `alembic downgrade base`
запрещён. Каждая новая миграция в примечаниях к релизу помечается: «откат безопасен» или «только
восстановление из копии».

## 5. Обновление базовых образов

Ежемесячно или при уязвимости: `scripts/pin_images.sh` → `make check scan backup-selftest` →
коммит `deploy/images.lock.env` → выпуск релиза.

Trivy не видит интерпретатор Python, PostgreSQL, Redis и Caddy, собранные из исходного кода в
официальных образах: в SBOM они присутствуют как `pkg:generic` только для учёта состава. Поэтому
исправления их уязвимостей приходят только через обновление базовых образов (`pin_images.sh`), а
контроль — это ежемесячный цикл выше плюс отслеживание сообщений об уязвимостях разработчиков этих
продуктов службой ИБ (в системе не автоматизировано). Исключения сканера — в
[../security/sast-exceptions.md](../security/sast-exceptions.md).

Раз в месяц в том же цикле: обновить закреплённые по SHA GitHub Actions в `.github/workflows/ci.yml`
(Dependabot или вручную) и проверить версии образов инструментов в `deploy/compose.tools.yml`
([../security/sbom.md](../security/sbom.md), «Инструменты разработки и CI»). Релиз не подписывается
цифровой подписью: целостность обеспечивает `SHA256SUMS`, переданный по отдельному каналу.

## 6. Выпуск релиза (контрольный список)

- [ ] `make check` и `make scan` зелёные (`make release` повторяет `make scan` внутри); реестр исключений ([../security/sast-exceptions.md](../security/sast-exceptions.md)) пересмотрен.
- [ ] `make backup-selftest` зелёный; E2E (`make e2e`, в CI — `make e2e-ci`) зелёные.
- [ ] Нагрузочный тест на тестовом контуре — протокол приложен ([load-test.md](load-test.md)).
- [ ] Примечания к релизу: миграции и возможность их отката.
- [ ] `make release VERSION=…`, контрольные суммы переданы по отдельному каналу.
