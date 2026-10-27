# Журнал аудита

Реализация: `backend/app/audit/service.py`, миграция `backend/migrations/versions/0004_audit.py`.
Требования: ТЗ, раздел 9 («Аудит»), спецификация, раздел 3.6.

## 1. Регистрируемые события

| Код | Событие |
|---|---|
| `auth.login.ok` / `auth.login.fail` | успешный / неуспешный вход |
| `auth.password.ok` | пароль принят, запрошен второй фактор |
| `auth.mfa.fail`, `auth.mfa.enrolled`, `auth.mfa.backup_code_used` | ошибка второго фактора, подключение 2FA, использование резервного кода |
| `auth.logout`, `auth.session.revoked` | выход, завершение сеанса |
| `auth.password.changed`, `auth.password.change_fail` | смена пароля, неуспешная попытка |
| `admin.user.created`, `admin.user.updated`, `admin.user.blocked`, `admin.user.unblocked` | управление пользователями |
| `admin.user.password_reset`, `admin.user.mfa_reset` | сброс пароля и 2FA администратором |
| `admin.role.created`, `admin.role.updated`, `admin.position.created`, `admin.position.updated` | изменение ролей и должностей (смена прав) |
| `admin.key.rotated`, `admin.key.retired`, `admin.key.rewrapped` | операции с ключами шифрования: ротация DEK, вывод версий, смена KEK |
| `admin.etl.run_requested`, `etl.run.started`, `etl.run.finished` | запуски загрузок и их результат |
| `admin.build.rolled_back`, `dwh.partitions.dropped` | откат сборки витрины, удаление устаревших партиций |
| `admin.alert_rule.updated`, `admin.fin_assumptions.updated`, `admin.setting.updated` | изменение порогов и допущений финмодели, настроек |
| `admin.integration.updated`, `admin.integration.check_requested` | изменение параметров и учётных данных интеграций (только факт «задан/удалён», без значения), запрос проверки подключения |
| `auth.step_up.failed` | неверный код 2FA при подтверждении изменения настройки |
| `audit.exported`, `audit.verified` | выгрузка журнала, проверка цепочки |
| `ops.restore_test.recorded` | результат ежемесячной проверки восстановления |
| `security.rls_violation_attempt` | попытка запросить данные вне своей области |
| `security.access_denied` | отказ в доступе (нет разрешения) |

Выгрузки данных (xlsx/csv по разделам) журналируются по мере появления разделов (следующие этапы):
сейчас разрешения на выгрузку заведены, а единственная реализованная выгрузка — журнал аудита
(`audit.exported`).

## 2. Состав записи

`id`, `ts` (UTC), `user_id`, `action`, `result` (`ok`/`fail`/`denied`), `object_type`, `object_id`,
`request_id` (совпадает с заголовком `X-Request-ID` ответа), `details` (JSON), `ip_enc`, `ua_enc`,
`chain_key_version`, `prev_hash`, `hash`. IP и User-Agent зашифрованы (AES-256-GCM, ключ
`audit_meta`). Поля `details` проходят маскирование по имени поля (пароли, токены, коды, секреты,
ИНН, счета заменяются на `***`) и очистку (NUL, некорректные суррогаты, ограничение длины
служебных полей) — `test_sanitizes_hostile_details_and_still_verifies`.

## 3. Цепочка целостности

`hash = HMAC-SHA256(K[v], prev_hash ‖ канонический JSON записи)`, где `K[v]` — DEK `audit_chain`
версии `chain_key_version`. Ключ хранится обёрнутым KEK, поэтому даже имеющий право записи в БД не
может пересчитать цепочку. Запись выполняется только функциями `core.audit_reserve()` и
`core.audit_append()` (SECURITY DEFINER, владелец `ugk_migrator`), которые проверяют:
совпадение `prev_hash` с головой цепочки; что `id` выдан этим же сеансом из последовательности;
монотонность `id`; что `ts` отличается от часов СУБД не более чем на ±5 минут; что версия ключа
существует и не выведена. Ключ для проверки каждой записи выбирается по её `chain_key_version`, поэтому ротация
`audit_chain` не нарушает проверку старых записей. Параллельные записи упорядочиваются блокировкой головы цепочки
(`test_concurrent_records_keep_chain_valid`).

**Синхронизация времени обязательна**: при расхождении часов приложения и СУБД более 5 минут
запись аудита отклоняется и операция пользователя завершается ошибкой. На хосте работает chrony
([../ops/host-hardening.md](../ops/host-hardening.md)), расхождение более 60 с ops-check сообщает
как `clock_skew` (критично).

## 4. Права доступа

| Роль | Права на `core.audit_log`, `audit_head`, `audit_anchor` |
|---|---|
| `ugk_app` | только `SELECT`; запись — только через функции `audit_reserve()` / `audit_append()` |
| `ugk_etl` | нет прав на таблицы (запись — через функции; удаление устаревших партиций — функция `drop_old_audit_partitions()`, доступная только этой роли) |
| `ugk_migrator` | владелец; используется только оператором |

Тесты: `test_app_role_cannot_write_audit_tables_directly`, `test_app_role_cannot_write_audit_anchor`,
`test_app_role_cannot_setval_audit_sequence`, `test_etl_role_cannot_select_audit_log`.

## 5. Проверка

- Интерфейс: «Администрирование → Журнал аудита → Проверить целостность».
- API: `POST /api/v1/audit/verify` (разрешение `audit:read`); лимит 3 запроса за 10 минут на
  пользователя и 10 в час на всю систему (проверка читает всю таблицу). Результат проверки
  записывается событием `audit.verified` (`result = "fail"` при нарушении).
- Командная строка: `make audit-verify STACK=prod` (код возврата 2 при нарушении).

Проверка идёт от якоря `core.audit_anchor` (хеш последней удалённой по сроку записи) до головы
цепочки и сообщает **все** нарушения (до 100 идентификаторов; командная строка выводит первые 20):
изменение записи, удаление из середины, удаление начала без обновления якоря, подделку головы,
неизвестную версию ключа
(`test_tampering_in_two_places_reports_both_ids`, `test_deletion_in_the_middle_is_detected_and_then_repaired`,
`test_prefix_deletion_without_anchor_update_is_detected_and_then_repaired`,
`test_forged_head_is_detected_and_then_repaired`). Порядок действий при нарушении — сценарий СЦ3
в [incident-response.md](incident-response.md).

## 6. Хранение

Журнал разбит на месячные партиции; worker ежедневно (03:30 по Ташкенту) создаёт партиции на
3 месяца вперёд и удаляет партиции старше срока `retention.audit_months` (по умолчанию 12,
допустимо 12–120). Функция удаления в СУБД не допускает срок меньше 12 месяцев
(`test_drop_old_partitions_respects_12_month_floor`) и перед удалением переносит хеш последней
удаляемой записи в якорь. Записи, не попавшие в месячную партицию, остаются в `audit_log_default`;
их наличие ops-check сообщает как `audit_default_rows`, отсутствие партиции следующего месяца —
как `audit_partition_missing` (критично).

## 7. Доступ на чтение и выгрузка

Просмотр и выгрузка — разрешение `audit:read`: роли «Администратор» и «Служба внутреннего контроля»
(ТЗ, раздел 9). Выгрузка CSV (до 50 000 строк; при усечении добавляется заголовок
`X-Export-Truncated`) защищена от формульных инъекций и сама регистрируется событием
`audit.exported` (`test_export_csv_is_safe_and_audited`). IP-адрес расшифровывается только при
просмотре или выгрузке пользователем с правом `audit:read`; User-Agent хранится зашифрованным и
интерфейсом не выдаётся.

## 8. Ограничения

- Суперпользователь СУБД или root хоста может физически удалить данные; такие изменения
  обнаруживаются проверкой цепочки, но не предотвращаются (остаточный риск R5). Ключ `audit_chain`
  никогда не выводится из обращения: его утрата сделала бы проверку старых записей невозможной.
- Неуспешные административные изменения (конфликт версии 409, ошибка фиксации)
  журналируются только для операций с ключами (`result = "fail"`); для пользователей, ролей и
  настроек — запланировано (журнал доступа содержит запрос и код ответа).
