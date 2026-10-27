# Перечень программных компонентов (SBOM)

## Формат и состав

SBOM формируется в формате CycloneDX (JSON) инструментом Trivy при каждом `make scan` и при сборке
релиза (`scripts/scan.sh`, `scripts/release.sh`):

| Файл | Содержимое |
|---|---|
| `ugekazna-backend.cdx.json` | образ API/worker: пакеты Debian базового образа, Python-зависимости из `/opt/venv`, интерпретатор Python |
| `ugekazna-web.cdx.json` | образ Caddy со сборкой фронтенда: пакеты Alpine, Caddy |
| `ugekazna-db.cdx.json` | образ СУБД: пакеты Alpine, PostgreSQL 16, pgBackRest |
| `ugekazna-redis.cdx.json` | образ Redis |
| `frontend-npm.cdx.json` | npm-зависимости фронтенда по `frontend/package-lock.json` (Trivy по умолчанию не включает devDependencies) |

Интерпретатор Python, PostgreSQL, Redis и Caddy собраны в официальных образах из исходного кода, и
Trivy не видит их по метаданным пакетов: `scripts/sbom_runtime.py` добавляет их в SBOM как компоненты
`pkg:generic/python`, `pkg:generic/postgresql`, `pkg:generic/redis`, `pkg:generic/caddy` с версией из
окружения образа (`test_sbom_runtime_adds_components`).

Прямые зависимости и их версии также зафиксированы в lock-файлах с хешами:
`backend/requirements.txt`, `frontend/package-lock.json`; базовые образы — `deploy/images.lock.env`.

## Где находится

- Локально и в CI: каталог `build/sbom/` после `make scan`; в CI — артефакт `sbom` (90 дней).
- В пакете релиза: каталог `sbom/` рядом с образами, с контрольными суммами в `SHA256SUMS`.

## Проверка

`scripts/check_sbom.py` проверяет формат CycloneDX, наличие компонентов и обязательных пакетов:
в образе API — `fastapi`, `cryptography`, `argon2-cffi`, Python; в образе СУБД — `pgbackrest`,
PostgreSQL; в образах веб-сервера и Redis — Caddy и Redis; во фронтенде — `react`, `react-dom`.
Проверка выполняется в `make scan` (`test_check_sbom_accepts_valid`, `test_check_sbom_rejects_invalid`,
`test_check_sbom_group_and_shape`).

## Повторная проверка уязвимостей

Для установленного релиза без пересборки:

```bash
docker run --rm -v "$PWD/sbom:/sbom:ro" aquasec/trivy:0.57.1 sbom --severity HIGH,CRITICAL /sbom/ugekazna-backend.cdx.json
```

CI повторяет сканирование еженедельно (расписание `schedule` в `.github/workflows/ci.yml`; в GitLab
расписание задаётся в CI/CD → Schedules и в репозитории не хранится). Trivy в `make scan` сообщает
об уязвимостях HIGH и CRITICAL, для которых есть исправление; исключения перечислены в
`.trivyignore` и [sast-exceptions.md](sast-exceptions.md). Обнаруженная уязвимость обрабатывается по сценарию СЦ7
([incident-response.md](incident-response.md)).

## Инструменты разработки и CI

Образы инструментов (`node:22-alpine`, `mcr.microsoft.com/playwright:v1.49.1-noble`, сканеры в
`deploy/compose.tools.yml`) закреплены по версии тега, но не по digest: они не входят в поставку и не
запускаются в prod. В поставку входят только образы `ugekazna-*`, собранные из базовых образов по digest
(`deploy/images.lock.env`). Предупреждение для esbuild 0.21.5 (dev-сервер Vite,
`frontend/package-lock.json`) к поставке не относится: dev-сервер не используется, `npm audit --omit=dev`
проверяет только production-зависимости. То же относится к образам сканеров и k6
(`aquasec/trivy:0.57.1`, `zricethezav/gitleaks:v8.21.2`, `semgrep/semgrep:1.95.0`, `hadolint/hadolint:v2.12.0`,
`grafana/k6:0.54.0`): они закреплены тегом (изменяемым), а наборы правил semgrep (`p/owasp-top-ten`,
`p/python`, `p/typescript`, `p/react`) загружаются из сети при каждом запуске, поэтому результат
`make check` может меняться со временем. Закрепление по digest — запланировано.
