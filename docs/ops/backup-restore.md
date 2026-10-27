# Резервное копирование и восстановление

## 1. Что и когда копируется

| Что | Когда (Ташкент) | Кем |
|---|---|---|
| Полная копия | ежедневно 01:00 (`BACKUP_FULL_AT=2000` в UTC) | сервис `backup` (`ugk-backup loop`) |
| Разностная копия | 07:00, 13:00, 19:00 (`BACKUP_DIFF_AT=0200 0800 1400` в UTC) | сервис `backup` |
| Журнал транзакций (WAL) | непрерывно, не реже чем раз в 15 минут (`archive_timeout = 15min`) | PostgreSQL `archive_command` → pgBackRest |

Итог: RPO (потеря данных) — не более 15 минут; RTO (время восстановления) — не более 2 часов
(ТЗ, раздел 9). Хранится 14 полных копий, 12 последних разностных и WAL в пределах хранимых копий
(`repo1-retention-full`, `repo1-retention-diff`). Репозиторий зашифрован (AES-256-CBC средствами pgBackRest, пароль `pgbackrest_cipher_pass`) и
должен находиться на отдельном зашифрованном носителе (требование к хосту) (`/srv/ugk-backup`, том `ugk_pgbackrest_repo`).
Файлы данных и конфигурация — `deploy/pgbackrest/pgbackrest.conf`, расписание — `deploy/compose.prod.yml`.

Для восстановления, кроме репозитория, нужны секреты на момент копии: `pgbackrest_cipher_pass`,
`master_kek` (им обёрнуты ключи в копии), пароли ролей — хранятся в сейфе
([../security/key-management.md](../security/key-management.md), П2).

## 2. Контроль

- `make backup-status` — список копий (`pgbackrest info`) и результат последней проверки восстановления.
- Healthcheck сервиса `backup` переходит в `unhealthy`, если последняя копия завершилась ошибкой или
  успешной копии нет более 7 часов; это видит `monitor.sh` ([monitoring.md](monitoring.md)).
- Журнал: `$P logs backup` — события `backup_started`, `backup_ok`, `backup_failed` в JSON.
- Журнал WAL: `ops-check` сообщает `wal_archiver_failed` и `wal_archiver_lag`, если архивирование WAL
  не работает (RPO 15 минут иначе не обеспечивается; только возраст копии виден через ~7 часов).

## 3. Внеочередная копия

`make backup` (полная) или `make backup TYPE=diff`; перед обновлением — обязательно
([install-upgrade.md](install-upgrade.md), раздел 3).

## 4. Ежемесячная проверка восстановления

Выполняется автоматически в первую субботу месяца в 21:00 по Ташкенту (таймер
`ugekazna-restore-test.timer`, журнал в `/var/log/ugekazna`) и вручную командой
`UGK_LOG_DIR=/var/log/ugekazna make restore-test` (`scripts/restore_test.sh`):

1. Берётся последняя копия; во временном проекте Docker (`ugekazna-restore`, изолированная сеть,
   репозиторий только на чтение) выполняется восстановление с воспроизведением WAL до конца архива;
   архивирование в восстановленной копии отключено.
2. Проверки: ревизия схемы (`alembic current` = head), целостность журнала аудита (`audit-verify`),
   число строк в основных таблицах, общее время не более 7200 с.
3. Результат записывается в журнал `/var/log/ugekazna/restore-test-<время>.log` и в систему
   (`last_restore_test`, событие аудита `ops.restore_test.recorded`); просмотр — `make backup-status`.
4. Временная копия удаляется. `UGK_RESTORE_KEEP=1` оставляет её для анализа (копия содержит полные
   данные prod — храните только на время расследования). Удаление после анализа (переменные окружения
   нужны для разбора `compose.restore.yml`):
   ```bash
   docker compose -p ugekazna-restore -f deploy/compose.restore.yml \
     --env-file deploy/prod.env --env-file deploy/release.env down -v --remove-orphans
   ```

Результат записывается через сервис `migrate` в работающую базу prod, поэтому prod-стек во время
проверки должен быть запущен. Коды завершения: 0 — успешно; 1 — ошибка проверки; 3 — в репозитории
нет копий. Отсутствие проверки более 35 дней или ошибка — оповещение ops-check
(`restore_test_overdue`, `restore_test_failed`, `restore_test_missing`); таймер при ненулевом коде
завершения вызывает запись crit в syslog (`ugekazna-alert`). Сама процедура проверяется автоматизированным тестом `make backup-selftest`; он входит в чек-лист выпуска релиза
([install-upgrade.md](install-upgrade.md), раздел 6), а не в CI.

## 5. Аварийное восстановление рабочей системы

Применяется при потере или повреждении данных (сценарий СЦ6 в
[../security/incident-response.md](../security/incident-response.md)).

1. Определить точку восстановления: последняя копия или момент времени до повреждения.
2. Остановить сервисы и сохранить повреждённый том (при наличии места):
   ```bash
   $P rm -fs caddy api worker backup db
   docker run --rm --entrypoint tar -v ugekazna_db_data:/from:ro ugekazna-db:<версия> \
     -C /from -czf - . > /srv/ugk-backup/db_data-before-restore.tar.gz
   docker volume rm ugekazna_db_data
   ```
   Том `db_data` подключён к контейнерам `db` и `backup` (в остановленном состоянии тоже), поэтому их
   нужно удалить (`rm -fs`), иначе Docker откажется удалять том. Новый том создаст `$P run` на шаге 3.
   Архив повреждённого тома кладётся на тот же носитель, что и репозиторий копий: проверьте свободное
   место заранее.
3. Восстановление (архивирование после восстановления сохраняется — новая линия времени продолжает
   писать WAL в репозиторий):
   ```bash
   $P run --rm -T --no-deps -e UGK_RESTORE_KEEP_ARCHIVING=yes db ugk-restore
   # на момент времени:
   $P run --rm -T --no-deps -e UGK_RESTORE_KEEP_ARCHIVING=yes db ugk-restore --type=time --target="2026-09-25 10:00:00+05" --target-action=promote
   ```
   `ugk-restore` отказывается работать в непустом каталоге данных (код 3). Без `--target-action=promote`
   pgBackRest по умолчанию останавливает воспроизведение WAL на цели в режиме паузы; тогда после запуска
   выполните `SELECT pg_wal_replay_resume()`. PostgreSQL воспроизводит WAL при первом запуске (шаг 4).
4. Запуск и проверки: `$P up -d`; `$P ps`; вход; `make audit-verify STACK=prod`; сверка данных за
   последние сутки с учётными системами; `make backup` (новая полная копия).
5. Запись в журнал инцидента: точка восстановления, время начала и окончания (RTO), потерянный
   интервал (RPO).

Восстановление на новом сервере: подготовка по [host-hardening.md](host-hardening.md), установка
того же релиза ([install-upgrade.md](install-upgrade.md); вместо шага 3 — возврат секретов из сейфа, шаг 6
не выполняется),
подключение носителя копий, шаги 3–5 этого раздела. Порядок: до запуска стека (`$P up -d`) том `db_data`
должен быть пуст и восстановлен шагом 3; запуск `$P up -d` на пустом томе создаст новый кластер и
попытается сделать первую полную копию (`UGK_BACKUP_INITIAL_FULL`), поэтому на новом сервере
установите `UGK_BACKUP_INITIAL_FULL=no` до восстановления и верните `yes` после.
