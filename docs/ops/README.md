# Эксплуатационная документация UGEKAZNA

| Документ | Для кого | Содержание |
|---|---|---|
| [host-hardening.md](host-hardening.md) | администратор ОС | подготовка и укрепление сервера: LUKS2, SSH, межсетевой экран, время, auditd, обновления, Docker |
| [install-upgrade.md](install-upgrade.md) | администратор ОС | установка, обновление, откат, политика отката миграций |
| [backup-restore.md](backup-restore.md) | администратор ОС | резервное копирование, ежемесячная проверка, аварийное восстановление |
| [monitoring.md](monitoring.md) | администратор ОС, служба ИТ | контроль состояния, оповещения, реакция |
| [load-test.md](load-test.md) | служба ИТ, приёмка | нагрузочный тест и протокол |
| [admin-guide.md](admin-guide.md) | администратор приложения | пользователи, должности и роли, 2FA, журнал аудита, ключи |
| [user-guide.md](user-guide.md) | пользователи | вход, 2FA, фильтры, выгрузка и печать |

Документы по безопасности: [../security/README.md](../security/README.md).

Все команды на сервере выполняются в каталоге текущего релиза `/opt/ugekazna/current`; сокращение:

```bash
P="docker compose -f deploy/compose.prod.yml --env-file deploy/prod.env --env-file deploy/release.env"
```

Docker Compose-проект prod и dev-стенда называется одинаково (`ugekazna`). На сервере с
`deploy/prod.env` команды `make` для dev-стенда (`up`, `down`, `seed-synthetic` и др.) отказывают;
операторские команды выполняются с `STACK=prod` (например `make audit-verify STACK=prod`) или через
`$P`. Не запускайте на prod-сервере `docker compose -f deploy/compose.yml …`: `down` удалил бы prod-стек.

Часы работы и обслуживание (ТЗ, раздел 9): доступность в рабочее время 08:00–20:00 по Ташкенту не
ниже 99 %; плановые работы — вне рабочего времени с предупреждением пользователей.
