# Подготовка и укрепление сервера

Целевая ОС — Ubuntu Server 24.04 LTS (для Debian 12 команды совпадают). Выполняется до установки
системы; каждый пункт завершается проверкой. Сводный список — раздел 10.

## 0. Требования

| Параметр | Профиль 8 ГБ | Профиль 16 ГБ |
|---|---|---|
| Процессор | 4 vCPU | 8 vCPU |
| Память | 8 ГБ (`UGK_PG_PROFILE=8gb`, `UGK_DB_MEM=4g`) | 16 ГБ (`UGK_PG_PROFILE=16gb`, `UGK_DB_MEM=9g`, `UGK_DB_CPUS=4`) |
| Системный диск | 40 ГБ | 40 ГБ |
| Диск данных Docker | 200 ГБ SSD, LUKS2 | 400 ГБ SSD, LUKS2 |
| Носитель резервных копий | отдельный физический диск или СХД, не менее 3× объёма БД, LUKS2 | то же |

Сеть: адрес во внутренней сети, доступный из подсетей VPN; DNS-имя сервера совпадает с именем в
сертификате (`UGK_DOMAIN`); доступ сервера к SMTP-релею и DNS организации.

## 1. Шифрование дисков (LUKS2)

Диск данных Docker (`/var/lib/docker`) и носитель копий шифруются LUKS2 с AES-256-XTS:

```bash
cryptsetup luksFormat --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --pbkdf argon2id /dev/sdb
cryptsetup open /dev/sdb ugk-data
mkfs.ext4 -L ugk-data /dev/mapper/ugk-data
cryptsetup luksFormat --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --pbkdf argon2id /dev/sdc
cryptsetup open /dev/sdc ugk-backup
mkfs.ext4 -L ugk-backup /dev/mapper/ugk-backup
mkdir -p /var/lib/docker /srv/ugk-backup
```

`/etc/crypttab`:
```
ugk-data    /dev/sdb  none  luks,discard,tpm2-device=auto
ugk-backup  /dev/sdc  none  luks,tpm2-device=auto
```
`/etc/fstab`:
```
/dev/mapper/ugk-data    /var/lib/docker  ext4  defaults,noatime,nodev,nosuid  0 2
/dev/mapper/ugk-backup  /srv/ugk-backup  ext4  defaults,noatime,nodev,nosuid,noexec  0 2
```

Разблокировка при загрузке — TPM2 (`systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 /dev/sdb`,
то же для `/dev/sdc`) и отдельный пароль восстановления (`cryptsetup luksAddKey`), который хранится в
сейфе. Без TPM2 пароль вводится при загрузке через консоль управления.

Проверка: `cryptsetup luksDump /dev/sdb | grep -E 'Version|cipher'` → `Version: 2`, `aes-xts-plain64`.

## 2. Учётные записи и SSH

- Администраторы — именные учётные записи в группе `ugk-admins`; `sudo` только для неё.
- Группа `docker` даёт права root: в неё входят только члены `ugk-admins`.
- Вход — только по ключам (ed25519), с адресов VPN.

`/etc/ssh/sshd_config.d/10-ugekazna.conf`:
```
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthenticationMethods publickey
AllowGroups ugk-admins
MaxAuthTries 3
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
KexAlgorithms sntrup761x25519-sha512@openssh.com,curve25519-sha256,curve25519-sha256@libssh.org
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
```
Применение: `sshd -t && systemctl reload ssh`. Проверка: `sshd -T | grep -E 'passwordauthentication|permitrootlogin'`.

## 3. Межсетевой экран (ufw и DOCKER-USER)

Пример: подсеть VPN `10.10.0.0/16`, внешний интерфейс `ens18`, SMTP-релей `10.20.0.25`, DNS
`10.20.0.53` — замените значениями организации.

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow from 10.10.0.0/16 to any port 22 proto tcp
ufw enable
```

Docker публикует порты в обход правил INPUT ufw, поэтому трафик к контейнерам ограничивается в
цепочке `DOCKER-USER`. Пакеты в ней уже прошли DNAT — указываются порты контейнера (8443, 8080), а не
443/80. Добавьте в конец `/etc/ufw/after.rules`:
```
*filter
:DOCKER-USER - [0:0]
-A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
-A DOCKER-USER -i ens18 -s 10.10.0.0/16 -p tcp -m multiport --dports 8443,8080 -j RETURN
-A DOCKER-USER -i ens18 -j DROP
# SMTP: 25/587 (STARTTLS) и 465 (SMTP_SSL=true) — оставьте только порт, выбранный в prod.env
-A DOCKER-USER -o ens18 -d 10.20.0.25 -p tcp -m multiport --dports 25,465,587 -j RETURN
-A DOCKER-USER -o ens18 -d 10.20.0.53 -p udp --dport 53 -j RETURN
-A DOCKER-USER -o ens18 -j DROP
-A DOCKER-USER -j RETURN
COMMIT
```
Дополнительно в `prod.env` задаётся `UGK_BIND_ADDR` — адрес интерфейса в сторону VPN. После
подключения коннектора 1С добавляется разрешение на его адрес и порт.

**Выход в интернет для AI-анализа (раздел S5).** По умолчанию `api` в сеть `egress` не входит.
Только при запуске с `deploy/compose.ai.yml` (после согласования ИБ) `api` обращается к
`api.anthropic.com:443`. Рекомендуемый путь — тот же корпоративный прокси (`EGRESS_PROXY`) с
разрешённым доменом `api.anthropic.com`; правило `DOCKER-USER` для прокси уже задано для `worker`.
Без прокси — разрешить адреса `api.anthropic.com` на порт 443 (списки IP сопровождаются).

`compose.ai.yml` задаёт `AI_EGRESS=1`: в prod `api` не запустится, если `EGRESS_PROXY` пуст
(`Settings.problems()`), кроме явного `AI_DIRECT_EGRESS=ack`. `NO_PROXY` исключает `db`, `redis`,
`caddy`, `localhost`. Правило хоста — обязательная вторая линия: исходящий трафик контейнера `api`
(адрес в сети `egress`, `docker network inspect`) разрешён только на адрес прокси и порт 3128/8080,
остальное в `DOCKER-USER` запрещено:
```
-A DOCKER-USER -s <адрес api в egress> -d <адрес прокси> -p tcp --dport 3128 -j RETURN
-A DOCKER-USER -s <адрес api в egress> -o ens18 -j DROP
```
Проверка: из контейнера `api` прямой запрос на внешний адрес без прокси не проходит.

Применение: `ufw reload`. Проверка: `ufw status verbose`, `iptables -S DOCKER-USER`; с машины вне VPN
порт 443 недоступен.

## 4. Время (chrony) — обязательно

Точное время обязательно: функция записи журнала аудита отклоняет запись, если время события
отличается от часов СУБД более чем на 5 минут; коды TOTP действуют 30 секунд; от времени зависят сроки сертификатов и
сроки обслуживания и расписание резервных копий.

```bash
apt install -y chrony
cat > /etc/chrony/sources.d/ugekazna.sources <<'EOF'
server ntp1.uge.local iburst
server ntp2.uge.local iburst
EOF
systemctl restart chrony
```
Проверка: `chronyc tracking` — `System time` не более 0,1 с, `Leap status: Normal`. Расхождение часов
приложения и СУБД более 60 с система сообщает сама (`ops-check`, код `clock_skew`); это контроль
согласованности контейнеров, а не синхронизации с источником времени, поэтому chrony обязателен. Приложение и
СУБД работают в UTC; часовой пояс хоста на них не влияет.

## 5. Журнал аудита ОС (auditd)

```bash
apt install -y auditd audispd-plugins
```
`/etc/audit/rules.d/ugekazna.rules`:
```
-w /etc/docker/ -p wa -k ugk_docker
-w /usr/bin/dockerd -p x -k ugk_docker
-w /usr/bin/docker -p x -k ugk_docker_cli
-w /opt/ugekazna/shared/ -p rwa -k ugk_secrets
-w /etc/ssh/sshd_config -p wa -k ugk_ssh
-w /etc/ssh/sshd_config.d/ -p wa -k ugk_ssh
-w /etc/sudoers -p wa -k ugk_priv
-w /etc/sudoers.d/ -p wa -k ugk_priv
-w /etc/passwd -p wa -k ugk_identity
-w /etc/group -p wa -k ugk_identity
-w /etc/shadow -p wa -k ugk_identity
-w /etc/chrony/ -p wa -k ugk_time
-a always,exit -F arch=b64 -S adjtimex,settimeofday,clock_settime -k ugk_time
-a always,exit -F arch=b64 -S execve -F euid=0 -F auid>=1000 -F auid!=unset -k ugk_root_cmd
```
`/etc/audit/auditd.conf`: `max_log_file = 50`, `num_logs = 20`, `max_log_file_action = ROTATE`.
Применение: `augenrules --load`. Проверка: `auditctl -l | grep ugk`. Передача журналов в SIEM — раздел 9.

## 6. Обновления безопасности (unattended-upgrades)

```bash
apt install -y unattended-upgrades
```
`/etc/apt/apt.conf.d/52ugekazna`:
```
Unattended-Upgrade::Allowed-Origins { "${distro_id}:${distro_codename}-security"; };
Unattended-Upgrade::Package-Blacklist { "docker-ce"; "docker-ce-cli"; "containerd.io"; "docker-compose-plugin"; };
Unattended-Upgrade::Automatic-Reboot "false";
```
Пакеты Docker и перезагрузки — только в окно обслуживания. Проверка: `unattended-upgrade --dry-run -d`.

## 7. Docker Engine

Установка из официального репозитория Docker (Engine ≥ 24, Compose plugin ≥ 2.24).
`/etc/docker/daemon.json` — **до первого запуска контейнеров**:
```json
{
  "userns-remap": "default",
  "live-restore": true,
  "no-new-privileges": true,
  "icc": false,
  "userland-proxy": false,
  "log-driver": "json-file",
  "log-opts": { "max-size": "20m", "max-file": "5" },
  "default-ulimits": { "nofile": { "Name": "nofile", "Soft": 65536, "Hard": 65536 } }
}
```

- `userns-remap` — root в контейнере не является root на хосте (пользователь `dockremap`). Включать до
  создания томов: данные хранятся в отдельном каталоге `/var/lib/docker/<uid>.<gid>/`.
- При `userns-remap` владельцы файлов на хосте сдвигаются на базу из `/etc/subuid` (`/etc/subgid`),
  обычно 165536 (значение берите из файла, не из этого документа): группа секретов — база + 10001 (учитывает
  `scripts/secrets_perms.sh`), владелец каталога репозитория копий — база + 70. База:
  `awk -F: '$1 == "dockremap" { print $2; exit }' /etc/subgid`.
- `live-restore` — перезапуск dockerd без остановки контейнеров; `no-new-privileges` — по умолчанию для
  всех контейнеров; `icc: false` — запрет обмена на сети по умолчанию.

Применение: `systemctl restart docker`. Проверка: `docker info --format '{{.SecurityOptions}}'` содержит
`name=userns`; `grep dockremap /etc/subuid /etc/subgid`.

## 8. Каталоги

| Путь | Назначение | Владелец и права |
|---|---|---|
| `/opt/ugekazna/releases/ugekazna-<версия>/` | распакованные пакеты релизов | root, 0755 |
| `/opt/ugekazna/current` | ссылка на действующий релиз | root |
| `/opt/ugekazna/shared/prod.env` | параметры площадки | root, 0640 |
| `/opt/ugekazna/shared/secrets/` | секреты | root:<группа 10001 или 175537>, каталог 0750, файлы 0440 |
| `/srv/ugk-backup/repo` | репозиторий pgBackRest | uid 70 (при userns-remap — база из `/etc/subgid` + 70), 0750 |
| `/var/log/ugekazna/` | журналы проверки восстановления и инцидентов | root, 0750 |

## 9. Журналы и SIEM (обязательно)

Система сама не доставляет оповещения никуда, кроме письма через `worker` (SMTP). Если `worker` не
запущен или SMTP недоступен, о проблеме остаётся только запись в журнал хоста, поэтому на хосте
должна быть настроена пересылка в SIEM организации:

- syslog/journald с идентификаторами `ugekazna-monitor`, `ugekazna-alert` (запись уровня crit при сбое
  юнита systemd) и `ugekazna-restore-test`;
- `/var/log/audit/` (auditd);
- журналы контейнеров `/var/lib/docker/containers/*/*-json.log` (журнал доступа Caddy, события
  приложения и `ugk-backup`).

Проверка: тестовая запись `logger -t ugekazna-alert -p user.crit test` должна появиться в SIEM.

Таймеры используют часовой пояс `Asia/Tashkent` в `OnCalendar`, поэтому нужен systemd версии не ниже
235 (в Ubuntu 24.04 — 255). Юниты `deploy/systemd/*.service` используют `ProtectHome=read-only`, а не `yes`: плагин `docker compose`,
установленный для root в `/root/.docker/cli-plugins`, должен оставаться читаемым; не заменяйте значение
на `yes`.

## 10. Проверочный список

- [ ] LUKS2 на дисках данных и копий, пароль восстановления в сейфе.
- [ ] SSH: только ключи, без root, группа `ugk-admins`, доступ только из VPN.
- [ ] ufw включён, правила DOCKER-USER применены, порт 443 недоступен вне VPN.
- [ ] chrony синхронизирован (`chronyc tracking`).
- [ ] auditd с правилами `ugk_*`.
- [ ] unattended-upgrades только для обновлений безопасности, Docker исключён.
- [ ] Пересылка syslog, auditd и журналов контейнеров в SIEM настроена и проверена (раздел 9).
- [ ] `/etc/docker/daemon.json` применён, `userns-remap` активен до создания томов.
- [ ] Каталоги раздела 8 созданы с указанными правами.
