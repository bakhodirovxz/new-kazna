# UGEKAZNA 1-reja: Backend yadrosi (infra + xavfsizlik) — implementatsiya rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Docker'da ishlaydigan FastAPI backend yadrosini qurish: konfiguratsiya va sirlar, PostgreSQL sxemalari va DB rollari, AES-256-GCM envelope shifrlash, lokal akkauntlar + majburiy TOTP 2FA, sessiyalar/CSRF, RBAC + RLS konteksti, hash-chain audit, admin va audit API, kalit rotatsiyasi.

**Architecture:** Bitta Python paketi (`backend/app`) domen bo'yicha modullarga bo'lingan (`core`, `auth`, `audit`, `admin`, `health`). Sinxron SQLAlchemy 2.0 + psycopg3; endpointlar `def` (threadpool). DB'ga uch xil rol bilan ulaniladi (`ugk_app`, `ugk_etl`, `ugk_migrator`); migratsiyalar Alembic'da xom SQL. Audit yozuvi har doim alohida qisqa tranzaksiyada (so'rov rollback bo'lsa ham yo'qolmaydi).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), psycopg 3, Alembic, Pydantic 2 + pydantic-settings, argon2-cffi, pyotp, segno, cryptography, redis-py, structlog; PostgreSQL 16, Redis 7; Docker Compose; pytest.

**Spec:** [docs/superpowers/specs/2026-09-24-poydevor-design.md](../specs/2026-09-24-poydevor-design.md)

Bu — poydevor spec'ining 4 rejasidan birinchisi. Keyingilari: 2 — Витрина + ETL + kesh + meta API; 3 — Frontend; 4 — Ops/CI/prod hardening.

## Global Constraints

- Python `>=3.12`; image `python:3.12-slim-bookworm`; PostgreSQL `postgres:16-alpine`; Redis `redis:7-alpine`.
- Bog'liqliklar `requirements.in` da diapazon bilan, `requirements.txt`/`requirements-dev.txt` da `pip-compile --generate-hashes` bilan qotiriladi; image `pip install --require-hashes`.
- Kodda, compose va `.env` da parol yo'q. Sirlar: Docker secrets (`/run/secrets/<nom>`) yoki (faqat test) env. Sir nomlari: `db_superuser_password`, `db_migrator_password`, `db_app_password`, `db_etl_password`, `redis_password`, `master_kek`, `blind_index_key`, `session_pepper`.
- `master_kek`, `blind_index_key`, `session_pepper` — base64, aynan 32 bayt.
- Argon2id standart profili: `time_cost=3, memory_cost=65536 (64 MiB), parallelism=4`. `fast_test` profili faqat `ENV=test` da.
- Parol: ≥12 belgi, 4 turdan kamida 3 tasi, logini bo'lmasin, keng tarqalgan ro'yxatda bo'lmasin, oxirgi 5 ta paroldan farq qilsin, 90 kunlik muddat.
- TOTP: RFC 6238, SHA-1, 30 s, 6 raqam, ±1 qadam, bitta qadamni qayta ishlatish taqiqlangan; 10 ta zaxira kod.
- Sessiya: 256-bit token, cookie `__Host-ugk_session` (`HttpOnly; Secure; SameSite=Strict; Path=/`), DB'da faqat `HMAC-SHA256(session_pepper, token)`; idle 30 daqiqa, absolyut 12 soat. CSRF: `__Host-ugk_csrf` cookie + `X-CSRF-Token` header.
- Login: 5 xato → 15 daqiqa blok; IP bo'yicha 10/daq; 2FA challenge 5 daqiqa, 5 urinish.
- Shifrmatn formati: `0x01 | key_version (2B big-endian) | nonce (12B) | ciphertext | tag (16B)`; AAD = `"ugk|{purpose}|{schema}.{table}.{column}:{pk}"`.
- API prefiksi `/api/v1`; xato formati `{"error": {"code", "message", "request_id", "params"?}}`; xabarlar ruscha.
- So'rov tanasi ≤ 1 MB; sahifa hajmi ≤ 500.
- Vaqt har doim UTC (`datetime.now(UTC)`), DB ulanishi `TimeZone=UTC`.
- Konteynerlarda ilova foydalanuvchisi `10001:10001`; kod root'ga tegishli, faqat o'qish uchun.
- Buyruqlar repo ildizidan (`C:\Users\uge226\Desktop\ugekazna`) Git Bash'da. Test buyrug'i:
  `TEST="docker compose -f deploy/compose.test.yml run --rm test"` — keyin `$TEST pytest ...`.
- Bind-mount'li `docker run` buyruqlari oldidan Windows'da `MSYS_NO_PATHCONV=1` va yo'l uchun `$(pwd -W)`.
- Har commit xabari oxirida bo'sh qatordan keyin: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Spec'dan ongli chetlanishlar (spec'ga ham yoziladi): (1) SQLAlchemy **sinxron** (adreska'da sinalgan, threadpool yetarli); (2) zaxira kodlar Argon2 emas, `HMAC-SHA256(session_pepper)` bilan (50-bit tasodifiy kod, 10 ta Argon2 tekshiruvi 3 s ga cho'zilardi).

## Review Focus

1. **TOTP replay ±1 oynada:** bir kod bilan ikki marta kirish mumkin bo'lmasligi, hatto ikkinchi urinish boshqa challenge orqali bo'lsa ham — Task 10 testi `test_totp_code_cannot_be_replayed`.
2. **Bir vaqtdagi audit yozuvlari (4 ta uvicorn worker):** zanjir buzilmasligi — Task 6 testi `test_concurrent_records_keep_chain_valid`.
3. **Kalit rotatsiyasidan keyin boshqa worker'dagi eskirgan keyring keshi:** yangi versiya bilan shifrlangan qiymat ochilishi — Task 3 testi `test_decrypt_refreshes_stale_cache`.
4. **Login registri va probellar:** `" Admin "`, `"ADMIN"` bitta akkauntga olib borishi va dublikat yaratib bo'lmasligi — Task 10 `test_login_username_is_normalized`, Task 11 `test_duplicate_username_case_insensitive`.
5. **Sessiya davomida bloklangan foydalanuvchi:** keyingi so'rov darhol 401 — Task 9 `test_blocked_user_session_rejected` va Task 11 `test_block_revokes_sessions`.

---

## Fayl tuzilishi

```
.gitattributes, .editorconfig, .gitignore (mavjud), README.md, Makefile
scripts/gen_secrets.py                 dev/prod sirlarini yaratish
deploy/compose.yml                     dev stack: db, redis, migrate, api, caddy
deploy/compose.test.yml                test stack: db, redis, test
deploy/postgres/initdb/01-roles.sh     DB rollari (ugk_migrator/app/etl)
deploy/caddy/Caddyfile.dev             TLS internal, xavfsizlik sarlavhalari, /api proksi
backend/Dockerfile, .dockerignore, pyproject.toml, alembic.ini
backend/requirements.in, requirements-dev.in (+ qulflangan .txt)
backend/certs/                         korporativ CA (ixtiyoriy)
backend/migrations/env.py, script.py.mako
backend/migrations/versions/0001_foundation.py   sxemalar, huquqlar, RLS funksiyasi
backend/migrations/versions/0002_crypto_keys.py
backend/migrations/versions/0003_identity.py
backend/migrations/versions/0004_audit.py
backend/app/__init__.py                __version__
backend/app/main.py                    create_app, lifespan
backend/app/bootstrap.py               ishga tushishdagi idempotent tayyorgarlik
backend/app/cli.py                     create-admin, rotate-key, retire-keys, rewrap-keys, audit-verify, cleanup
backend/app/core/config.py             Settings (env + /run/secrets)
backend/app/core/db.py                 engine (rol bo'yicha), sessiya, apply_rls
backend/app/core/crypto.py             AES-256-GCM Keyring, key wrap, blind index
backend/app/core/keystore.py           DEK'lar DB'da, keyring keshi, rotate/rewrap
backend/app/core/reencrypt.py          shifrlangan ustunlar reyestri, qayta shifrlash
backend/app/core/errors.py             xatolar va handler'lar
backend/app/core/logging.py            structlog JSON + maskalash
backend/app/core/middleware.py         request-id, xavfsizlik sarlavhalari, tana limiti
backend/app/core/request_meta.py       ClientMeta (ip, ua, request_id)
backend/app/core/ratelimit.py          Redis limitlari
backend/app/core/models.py             DeclarativeBase (schema=core)
backend/app/health/router.py           /healthz, /readyz
backend/app/auth/permissions.py        bo'limlar, ruxsatlar, rol seed'lari
backend/app/auth/seed.py               sync_reference
backend/app/auth/models.py             Role, Position, User, UserSession, ...
backend/app/auth/passwords.py          Argon2id, parol siyosati
backend/app/auth/data/common-passwords.txt.gz
backend/app/auth/totp.py               TOTP, QR, zaxira kodlar
backend/app/auth/sessions.py           sessiya yaratish/tekshirish/bekor qilish
backend/app/auth/context.py            AuthContext, get_ctx, require_perm
backend/app/auth/service.py            login, 2FA, parol almashtirish
backend/app/auth/schemas.py, router.py
backend/app/audit/service.py           record, verify_chain
backend/app/audit/schemas.py, router.py
backend/app/admin/schemas.py, service.py, router.py, keys_router.py
backend/tests/...                      har vazifaga mos test fayllari
```

---

### Task 1: Repozitoriy karkasi, konfiguratsiya, Docker test muhiti, `/healthz`

**Files:**
- Create: `.gitattributes`, `.editorconfig`, `backend/.dockerignore`, `backend/pyproject.toml`, `backend/requirements.in`, `backend/requirements-dev.in`, `backend/Dockerfile`, `backend/certs/README.md`, `backend/certs/organization-ca-3.crt` (nusxa), `backend/app/__init__.py`, `backend/app/core/__init__.py`, `backend/app/core/config.py`, `backend/app/health/__init__.py`, `backend/app/health/router.py`, `backend/app/main.py`, `backend/tests/__init__.py`, `deploy/compose.test.yml`, `deploy/postgres/initdb/01-roles.sh`, `scripts/gen_secrets.py`
- Test: `backend/tests/test_config.py`, `backend/tests/test_health.py`

**Interfaces:**
- Produces: `app.core.config.Settings`, `get_settings() -> Settings`, `ConfigError`, `DbRole = Literal["app","etl","migrator"]`, `Settings.pg_url(role) -> str`, `Settings.redis_url -> str`, `Settings.key_bytes(name) -> bytes`, `Settings.problems() -> list[str]`, `TEST_KEYS`; `app.main.create_app() -> FastAPI`; `app.health.router.router`.

- [ ] **Step 1: Repozitoriy fayllari**

`.gitattributes`:
```
* text=auto eol=lf
*.pdf binary
*.png binary
*.gz binary
*.woff2 binary
*.crt text eol=lf
```

`.editorconfig`:
```
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
indent_style = space
indent_size = 4

[*.{yml,yaml,json,ts,tsx,css,md}]
indent_size = 2

[Makefile]
indent_style = tab
```

`backend/.dockerignore`:
```
.venv
__pycache__
*.pyc
.pytest_cache
.mypy_cache
.ruff_cache
.coverage
htmlcov
tests
```

Korporativ CA nusxasi (TLS-inspeksiya qiluvchi proksi orqasida pip ishlashi uchun):
```bash
mkdir -p backend/certs
cp "C:/Users/uge226/Desktop/1C.1/adreska/ops/ci/corporate-ca/organization-ca-3.crt" backend/certs/
```

`backend/certs/README.md`:
```markdown
# Korporativ CA

Bu yerdagi `*.crt` fayllar (PEM) build va runtime image'ga o'rnatiladi —
TLS-inspeksiya qiluvchi proksi orqasida `pip` va tashqi HTTPS so'rovlar ishlashi uchun.
Papka bo'sh bo'lsa hech narsa o'zgarmaydi. Bu ochiq sertifikat, sir emas.
```

- [ ] **Step 2: Python loyiha fayllari**

`backend/pyproject.toml`:
```toml
[project]
name = "ugekazna-backend"
version = "0.1.0"
requires-python = ">=3.12"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-q --strict-markers --strict-config -p no:cacheprovider"
filterwarnings = ["error::DeprecationWarning"]

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["app", "tests"]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "A", "C4", "DTZ", "T20", "SIM", "RUF", "S"]
ignore = ["S101", "B008", "RUF001", "RUF002", "RUF003"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S105", "S106", "S311"]
"migrations/*" = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["app", "tests"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true
plugins = ["pydantic.mypy"]
exclude = ["migrations/"]

[[tool.mypy.overrides]]
module = ["tests.*"]
disallow_untyped_defs = false

[[tool.mypy.overrides]]
module = ["pyotp", "pyotp.*", "segno"]
ignore_missing_imports = true
```

`backend/requirements.in`:
```
# To'g'ridan-to'g'ri bog'liqliklar. Qulflash: make lock (requirements.txt, hash bilan).
fastapi>=0.115,<1
uvicorn[standard]>=0.34,<1
sqlalchemy>=2.0.36,<2.1
psycopg[binary,pool]>=3.2,<4
alembic>=1.14,<2
pydantic>=2.10,<3
pydantic-settings>=2.7,<3
argon2-cffi>=23.1
pyotp>=2.9,<3
segno>=1.6,<2
cryptography>=44
redis>=5.2,<7
structlog>=24.4
```

`backend/requirements-dev.in`:
```
-r requirements.in
pytest>=8.3
pytest-cov>=6.0
httpx>=0.28
ruff>=0.8
mypy>=1.14
bandit>=1.8
pip-audit>=2.7
pip-tools>=7.5
```

- [ ] **Step 3: Bog'liqliklarni qulflash**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W)/backend:/w" -w /w \
  -e PIP_CERT=/w/certs/organization-ca-3.crt \
  python:3.12-slim-bookworm sh -c "pip install -q 'pip-tools>=7.5' && \
  pip-compile -q --strip-extras --generate-hashes --allow-unsafe -o requirements.txt requirements.in && \
  pip-compile -q --strip-extras --generate-hashes --allow-unsafe -o requirements-dev.txt requirements-dev.in"
```
Expected: `backend/requirements.txt` va `backend/requirements-dev.txt` paydo bo'ladi, har qatorda `--hash=sha256:`. Agar proksi bo'lmasa va `PIP_CERT` xato bersa — `-e PIP_CERT=...` ni olib tashlang.

- [ ] **Step 4: Dockerfile**

`backend/Dockerfile`:
```dockerfile
# syntax=docker/dockerfile:1.7
# ── 1-bosqich: bog'liqliklar ────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
WORKDIR /build
COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN python -m venv /opt/venv \
 && if [ "$INSTALL_DEV" = "true" ]; then REQ=requirements-dev.txt; else REQ=requirements.txt; fi \
 && /opt/venv/bin/pip install --require-hashes --no-deps -r "$REQ"

# ── 2-bosqich: ishchi image ─────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates \
 && groupadd --gid 10001 ugk \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin ugk
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
# Kod root'ga tegishli: ilova foydalanuvchisi uni o'zgartira olmaydi.
COPY app/ /app/app/
COPY migrations/ /app/migrations/
COPY alembic.ini pyproject.toml /app/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/healthz', timeout=3)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header", "--no-access-log"]
```
(`--forwarded-allow-ips *` xavfsiz, chunki `api` porti tashqariga ochilmaydi — unga faqat Caddy yetadi.)

`backend/migrations/` hozircha bo'sh bo'lgani uchun `COPY` yiqilmasligi kerak — Task 2 gacha `backend/migrations/.gitkeep` yarating:
```bash
mkdir -p backend/migrations && touch backend/migrations/.gitkeep && touch backend/alembic.ini
```
(`alembic.ini` Task 2 da to'ldiriladi.)

- [ ] **Step 5: DB rollari skripti va test compose**

`deploy/postgres/initdb/01-roles.sh`:
```sh
#!/bin/sh
# Ilova uchun uchta DB roli (spec 3.4). Parollar Docker secrets'dan yoki (test) env'dan.
set -eu

secret() {
  file="/run/secrets/$1"
  if [ -r "$file" ]; then cat "$file"; else printenv "$2" || true; fi
}

MIGRATOR_PW="$(secret db_migrator_password DB_MIGRATOR_PASSWORD)"
APP_PW="$(secret db_app_password DB_APP_PASSWORD)"
ETL_PW="$(secret db_etl_password DB_ETL_PASSWORD)"

for v in "$MIGRATOR_PW" "$APP_PW" "$ETL_PW"; do
  if [ -z "$v" ]; then
    echo "01-roles.sh: DB rollari paroli topilmadi" >&2
    exit 1
  fi
done

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v migrator_pw="$MIGRATOR_PW" -v app_pw="$APP_PW" -v etl_pw="$ETL_PW" \
  -v dbname="$POSTGRES_DB" <<'SQL'
CREATE ROLE ugk_migrator LOGIN PASSWORD :'migrator_pw';
CREATE ROLE ugk_app LOGIN NOBYPASSRLS PASSWORD :'app_pw';
CREATE ROLE ugk_etl LOGIN NOBYPASSRLS PASSWORD :'etl_pw';
ALTER DATABASE :"dbname" OWNER TO ugk_migrator;
REVOKE ALL ON DATABASE :"dbname" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"dbname" TO ugk_migrator, ugk_app, ugk_etl;
ALTER SCHEMA public OWNER TO ugk_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SQL
```

`deploy/compose.test.yml`:
```yaml
# Test stack. Parollar va kalitlar — faqat test uchun ochiq qiymatlar
# (prod'da ishlatilsa Settings.problems() ishga tushirmaydi).
name: ugekazna-test

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: test-superuser
      POSTGRES_DB: ugekazna
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C.UTF-8"
      DB_MIGRATOR_PASSWORD: test-migrator
      DB_APP_PASSWORD: test-app
      DB_ETL_PASSWORD: test-etl
    volumes:
      - ./postgres/initdb:/docker-entrypoint-initdb.d:ro
    tmpfs:
      - /var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U postgres -d ugekazna"]
      interval: 2s
      timeout: 3s
      retries: 30

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--requirepass", "test-redis", "--save", ""]
    healthcheck:
      test: ["CMD", "redis-cli", "--no-auth-warning", "-a", "test-redis", "ping"]
      interval: 2s
      timeout: 3s
      retries: 30

  test:
    build:
      context: ../backend
      args:
        INSTALL_DEV: "true"
    image: ugekazna-backend:dev
    working_dir: /app
    environment:
      ENV: test
      ARGON2_PROFILE: fast_test
      BASE_URL: https://testserver
      DB_HOST: db
      DB_APP_PASSWORD: test-app
      DB_ETL_PASSWORD: test-etl
      DB_MIGRATOR_PASSWORD: test-migrator
      REDIS_HOST: redis
      REDIS_PASSWORD: test-redis
      MASTER_KEK: AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
      BLIND_INDEX_KEY: ICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj8=
      SESSION_PEPPER: QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl8=
      COVERAGE_FILE: /tmp/.coverage
    volumes:
      - ../backend:/app
    tmpfs:
      - /tmp
    depends_on:
      db: {condition: service_healthy}
      redis: {condition: service_healthy}
```

`scripts/gen_secrets.py`:
```python
"""deploy/secrets/ ichida barcha sirlarni yaratadi. Mavjud fayllarga tegmaydi.

Ishlatish:  python scripts/gen_secrets.py [papka]
Prod (Linux): keyin  chown root:10001 deploy/secrets/* && chmod 0440 deploy/secrets/*
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
from pathlib import Path

KEYS_32 = ("master_kek", "blind_index_key", "session_pepper")
PASSWORDS = (
    "db_superuser_password",
    "db_migrator_password",
    "db_app_password",
    "db_etl_password",
    "redis_password",
)


def _write(path: Path, value: str) -> None:
    if path.exists():
        sys.stdout.write(f"  mavjud, o'tkazib yuborildi: {path.name}\n")
        return
    path.write_text(value, encoding="ascii")
    os.chmod(path, 0o600)
    sys.stdout.write(f"  yaratildi: {path.name}\n")


def main(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in KEYS_32:
        _write(target / name, base64.b64encode(secrets.token_bytes(32)).decode("ascii"))
    for name in PASSWORDS:
        _write(target / name, secrets.token_urlsafe(32))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("deploy/secrets"))
```

- [ ] **Step 6: Testlarni yozish**

`backend/tests/__init__.py`: bo'sh fayl.

`backend/tests/test_config.py`:
```python
import base64

import pytest

from app.core.config import TEST_KEYS, ConfigError, Settings

GOOD_KEY = base64.b64encode(bytes(range(100, 132))).decode()


def make(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "master_kek": GOOD_KEY,
        "blind_index_key": GOOD_KEY,
        "session_pepper": GOOD_KEY,
        "db_app_password": "x",
        "redis_password": "y",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_key_bytes_decodes_32_bytes() -> None:
    assert make().key_bytes("master_kek") == bytes(range(100, 132))


def test_key_bytes_rejects_wrong_length() -> None:
    s = make(master_kek=base64.b64encode(b"short").decode())
    with pytest.raises(ConfigError, match="32 bayt"):
        s.key_bytes("master_kek")


def test_key_bytes_rejects_non_base64() -> None:
    with pytest.raises(ConfigError, match="base64"):
        make(master_kek="not base64 !!!").key_bytes("master_kek")


def test_no_problems_for_valid_test_settings() -> None:
    assert make(env="test").problems() == []


def test_prod_rejects_test_keys_http_and_fast_hash() -> None:
    test_key = sorted(TEST_KEYS)[0]
    s = make(env="prod", master_kek=test_key, base_url="http://x", argon2_profile="fast_test")
    joined = " | ".join(s.problems())
    assert "test kaliti" in joined
    assert "https" in joined
    assert "fast_test" in joined


def test_fast_hash_only_in_test_env() -> None:
    assert any("fast_test" in p for p in make(env="dev", argon2_profile="fast_test").problems())


def test_pg_url_escapes_password() -> None:
    url = make(db_app_password="p@ss:w/rd").pg_url("app")
    assert "p%40ss%3Aw%2Frd@" in url
    assert url.startswith("postgresql+psycopg://ugk_app:")
```

`backend/tests/test_health.py`:
```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz() -> None:
    with TestClient(create_app(), base_url="https://testserver") as client:
        response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 7: Image'ni yig'ib, testlar yiqilishini tekshirish**

Run: `docker compose -f deploy/compose.test.yml build test && $TEST pytest tests/test_config.py tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 8: Implementatsiya**

`backend/app/__init__.py`:
```python
"""UGEKAZNA backend."""

__version__ = "0.1.0"
```

`backend/app/core/__init__.py` va `backend/app/health/__init__.py`: bo'sh fayllar.

`backend/app/core/config.py`:
```python
"""Konfiguratsiya: muhit o'zgaruvchilari + Docker secrets (/run/secrets).

Ustuvorlik: konstruktor argumentlari > env > /run/secrets. Kodda hech qanday sir yo'q.
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETS_DIR = Path("/run/secrets")
DbRole = Literal["app", "etl", "migrator"]
KEY_FIELDS = ("master_kek", "blind_index_key", "session_pepper")

# deploy/compose.test.yml dagi ochiq test kalitlari. Prod'da ular bilan ishga tushmaydi.
TEST_KEYS = frozenset(
    {
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
        "ICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj8=",
        "QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl8=",
    }
)


class ConfigError(RuntimeError):
    """Xavfli yoki to'liq bo'lmagan konfiguratsiya."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    env: Literal["dev", "test", "prod"] = "dev"
    base_url: str = "https://localhost"
    argon2_profile: Literal["standard", "fast_test"] = "standard"

    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "ugekazna"
    db_app_user: str = "ugk_app"
    db_app_password: SecretStr = SecretStr("")
    db_etl_user: str = "ugk_etl"
    db_etl_password: SecretStr = SecretStr("")
    db_migrator_user: str = "ugk_migrator"
    db_migrator_password: SecretStr = SecretStr("")
    db_pool_size: int = 10
    db_statement_timeout_ms: int = 5000

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: SecretStr = SecretStr("")

    master_kek: SecretStr = SecretStr("")
    blind_index_key: SecretStr = SecretStr("")
    session_pepper: SecretStr = SecretStr("")

    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    password_max_age_days: int = 90
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    def pg_url(self, role: DbRole) -> str:
        user: str = getattr(self, f"db_{role}_user")
        password: SecretStr = getattr(self, f"db_{role}_password")
        return (
            f"postgresql+psycopg://{quote(user, safe='')}:"
            f"{quote(password.get_secret_value(), safe='')}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def redis_url(self) -> str:
        password = quote(self.redis_password.get_secret_value(), safe="")
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    def key_bytes(self, name: str) -> bytes:
        if name not in KEY_FIELDS:
            raise ConfigError(f"noma'lum kalit: {name}")
        raw: str = getattr(self, name).get_secret_value()
        try:
            value = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ConfigError(f"{name}: base64 emas") from exc
        if len(value) != 32:
            raise ConfigError(f"{name}: 32 bayt bo'lishi kerak")
        return value

    def problems(self) -> list[str]:
        """Bo'sh ro'yxat — ishga tushish mumkin. Aks holda ilova ishga tushmaydi."""
        out: list[str] = []
        for name in KEY_FIELDS:
            try:
                self.key_bytes(name)
            except ConfigError as exc:
                out.append(str(exc))
        if not self.db_app_password.get_secret_value():
            out.append("db_app_password bo'sh")
        if self.argon2_profile == "fast_test" and self.env != "test":
            out.append("argon2_profile=fast_test faqat test muhitida")
        if self.env == "prod":
            if not self.base_url.startswith("https://"):
                out.append("base_url https bo'lishi shart")
            if not self.redis_password.get_secret_value():
                out.append("redis_password bo'sh")
            for name in KEY_FIELDS:
                if getattr(self, name).get_secret_value() in TEST_KEYS:
                    out.append(f"{name}: test kaliti prod'da ishlatilmoqda")
        return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    secrets_dir = SECRETS_DIR if SECRETS_DIR.is_dir() else None
    return Settings(_secrets_dir=secrets_dir)  # type: ignore[call-arg]
```

`backend/app/health/router.py`:
```python
"""Liveness/readiness. Tashqi tarmoqqa Caddy orqali ochilmaydi."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

`backend/app/main.py`:
```python
"""FastAPI ilovasi."""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.health.router import router as health_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="UGEKAZNA API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(health_router, prefix=API_PREFIX)
    return app


app = create_app()
```

- [ ] **Step 9: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_config.py tests/test_health.py -v`
Expected: 8 passed.

- [ ] **Step 10: Commit**

```bash
git add .gitattributes .editorconfig backend deploy scripts
git commit -m "feat(backend): karkas, konfiguratsiya, Docker test muhiti va /healthz"
```

---

### Task 2: DB qatlami, Alembic, sxemalar va DB huquqlari, RLS konteksti

**Files:**
- Create: `backend/alembic.ini` (to'ldirish), `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/0001_foundation.py`, `backend/app/core/db.py`, `backend/tests/conftest.py`
- Modify: `backend/app/health/router.py` (readyz)
- Delete: `backend/migrations/.gitkeep`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Consumes: `get_settings()`, `Settings.pg_url(role)`.
- Produces: `app.core.db.get_engine(role: DbRole = "app") -> Engine`, `new_session() -> Session`, `get_db() -> Iterator[Session]` (commit/rollback), `apply_rls(db: Session, branch_ids: frozenset[int] | None) -> None` (`None` = barcha filiallar); SQL `core.rls_branch_ok(integer) -> boolean`; test fixture'lari `_database` (session, autouse), `db`.

- [ ] **Step 1: Alembic fayllari**

`backend/alembic.ini`:
```ini
[alembic]
script_location = migrations
prepend_sys_path = .

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)s [%(name)s] %(message)s
```

`backend/migrations/env.py`:
```python
"""Alembic: migratsiyalar faqat ugk_migrator roli bilan, xom SQL."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run() -> None:
    engine = create_engine(get_settings().pg_url("migrator"), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=None,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("offline rejim qo'llab-quvvatlanmaydi")
run()
```

`backend/migrations/script.py.mako`:
```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from alembic import op

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 2: 0001 migratsiyasi**

`backend/migrations/versions/0001_foundation.py`:
```python
"""sxemalar, sxema huquqlari, RLS funksiyasi

Revision ID: 0001
Revises:
Create Date: 2026-09-24
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = ("core", "stg", "dwh", "mart", "pub")


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA {schema}")
    op.execute("GRANT USAGE ON SCHEMA core TO ugk_app, ugk_etl")
    op.execute("GRANT USAGE ON SCHEMA pub TO ugk_app")
    op.execute("GRANT USAGE ON SCHEMA stg, dwh, mart TO ugk_etl")
    # RLS: filial doirasi tranzaksiya sozlamalaridan olinadi (app.core.db.apply_rls).
    # branch_id = 0 — "barcha filiallar jami" qatori, faqat scope_all uchun.
    op.execute(
        """
        CREATE FUNCTION core.rls_branch_ok(branch integer) RETURNS boolean
        LANGUAGE sql STABLE PARALLEL SAFE AS $$
          SELECT coalesce(current_setting('app.scope_all', true), '') = 'on'
              OR (branch <> 0 AND branch = ANY (
                    coalesce(nullif(current_setting('app.branch_ids', true), ''), '{}')::int[]))
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION core.rls_branch_ok(integer) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION core.rls_branch_ok(integer) TO ugk_app, ugk_etl")


def downgrade() -> None:
    op.execute("DROP FUNCTION core.rls_branch_ok(integer)")
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA {schema}")
```

```bash
rm backend/migrations/.gitkeep
```

- [ ] **Step 3: Testlarni yozish**

`backend/tests/conftest.py`:
```python
"""Umumiy fixture'lar. Testlar HAQIQIY PostgreSQL 16 va Redis'ga qarshi ishlaydi."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_engine, new_session


def _reset_core() -> None:
    """core sxemasidagi barcha jadvallarni tozalaydi (sessiya boshida bir marta)."""
    with get_engine("migrator").begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT format('%I.%I', schemaname, tablename) FROM pg_tables "
                    "WHERE schemaname = 'core' AND tablename <> 'audit_head'"
                )
            )
            .scalars()
            .all()
        )
        if tables:
            conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
        if conn.execute(text("SELECT to_regclass('core.audit_head')")).scalar() is not None:
            conn.execute(
                text(
                    "UPDATE core.audit_head SET last_id = NULL, "
                    "last_hash = decode(repeat('00', 32), 'hex')"
                )
            )


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    _reset_core()


@pytest.fixture
def db() -> Iterator[Session]:
    """ugk_app sessiyasi; test oxirida rollback."""
    session = new_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
```

`backend/tests/test_db.py`:
```python
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.db import apply_rls, get_engine, new_session
from app.main import create_app


@pytest.fixture
def rls_probe() -> Iterator[None]:
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS core.rls_probe"))
        conn.execute(text("CREATE TABLE core.rls_probe (id int, branch_id int NOT NULL)"))
        conn.execute(text("INSERT INTO core.rls_probe VALUES (1, 0), (2, 1), (3, 2)"))
        conn.execute(text("ALTER TABLE core.rls_probe ENABLE ROW LEVEL SECURITY"))
        conn.execute(text("ALTER TABLE core.rls_probe FORCE ROW LEVEL SECURITY"))
        conn.execute(
            text("CREATE POLICY p ON core.rls_probe USING (core.rls_branch_ok(branch_id))")
        )
        conn.execute(text("GRANT SELECT ON core.rls_probe TO ugk_app"))
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DROP TABLE core.rls_probe"))


def _visible(scope: frozenset[int] | None | str) -> list[int]:
    with new_session() as s:
        if scope != "unset":
            apply_rls(s, scope)  # type: ignore[arg-type]
        return sorted(s.execute(text("SELECT id FROM core.rls_probe")).scalars())


@pytest.mark.usefixtures("rls_probe")
def test_rls_scopes() -> None:
    assert _visible("unset") == []
    assert _visible(frozenset()) == []
    assert _visible(frozenset({1})) == [2]
    assert _visible(frozenset({1, 2})) == [2, 3]
    assert _visible(None) == [1, 2, 3]


@pytest.mark.usefixtures("rls_probe")
def test_rls_setting_is_transaction_local() -> None:
    with new_session() as s:
        apply_rls(s, None)
        assert len(s.execute(text("SELECT id FROM core.rls_probe")).all()) == 3
        s.commit()
        assert s.execute(text("SELECT id FROM core.rls_probe")).all() == []


def test_app_role_cannot_create_tables() -> None:
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("CREATE TABLE core.hack (id int)"))


def test_app_role_has_no_bypassrls() -> None:
    with new_session() as s:
        row = s.execute(
            text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")
        ).one()
    assert row == (False, False)


def test_readyz_reports_db() -> None:
    with TestClient(create_app(), base_url="https://testserver") as client:
        response = client.get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["db"] is True
```

- [ ] **Step 4: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.db'`.

- [ ] **Step 5: Implementatsiya**

`backend/app/core/db.py`:
```python
"""DB ulanishlari (rol bo'yicha), sessiyalar va RLS konteksti.

Sinxron SQLAlchemy: endpointlar `def`, Starlette ularni threadpool'da bajaradi.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DbRole, get_settings


@lru_cache(maxsize=3)
def get_engine(role: DbRole = "app") -> Engine:
    settings = get_settings()
    timeout = settings.db_statement_timeout_ms if role == "app" else 0
    options = (
        f"-c statement_timeout={timeout} "
        "-c idle_in_transaction_session_timeout=60000 -c TimeZone=UTC"
    )
    return create_engine(
        settings.pg_url(role),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_size,
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={"options": options, "application_name": f"ugekazna-{role}"},
    )


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine("app"), autoflush=False, expire_on_commit=False)


def new_session() -> Session:
    return _session_factory()()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: so'rov uchun bitta sessiya, oxirida commit yoki rollback."""
    db = new_session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


def apply_rls(db: Session, branch_ids: frozenset[int] | None) -> None:
    """Joriy tranzaksiya uchun filial doirasini o'rnatadi (SET LOCAL).

    `None` — barcha filiallar (scope_all). Bo'sh to'plam — hech narsa ko'rinmaydi.
    """
    ids = "{" + ",".join(str(int(b)) for b in sorted(branch_ids or ())) + "}"
    db.execute(
        text(
            "SELECT set_config('app.scope_all', :scope_all, true), "
            "set_config('app.branch_ids', :ids, true)"
        ),
        {"scope_all": "on" if branch_ids is None else "off", "ids": ids},
    )
```

`backend/app/health/router.py` — to'liq almashtiring:
```python
"""Liveness/readiness. Tashqi tarmoqqa Caddy orqali ochilmaydi."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.db import get_engine

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _db_ok() -> bool:
    try:
        with get_engine("app").connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


@router.get("/readyz")
def readyz() -> JSONResponse:
    checks = {"db": _db_ok()}
    ok = all(checks.values())
    return JSONResponse(
        {"status": "ok" if ok else "fail", "checks": checks},
        status_code=200 if ok else 503,
    )
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar (13) passed.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(db): Alembic, sxemalar va huquqlar, RLS konteksti, /readyz"
```

---

### Task 3: AES-256-GCM envelope shifrlash va kalitlar ombori

**Files:**
- Create: `backend/app/core/crypto.py`, `backend/app/core/keystore.py`, `backend/app/bootstrap.py`, `backend/migrations/versions/0002_crypto_keys.py`
- Modify: `backend/tests/conftest.py` (bootstrap chaqiruvi)
- Test: `backend/tests/test_crypto.py`, `backend/tests/test_keystore.py`

**Interfaces:**
- Consumes: `get_engine`, `Settings.key_bytes`.
- Produces:
  - `app.core.crypto`: `Purpose` (StrEnum: `PII="pii"`, `BANK="bank"`, `MFA="mfa"`, `INTEGRATION="integration_creds"`, `AUDIT="audit_meta"`), `CryptoError(reason: str)` (`.reason` ∈ `bad_format|unknown_key_version|integrity|no_active_key|unwrap_failed`), `Keyring(keys: Mapping[tuple[str,int], bytes], active: Mapping[str,int])` with `.encrypt(purpose, plaintext: bytes, aad: str) -> bytes`, `.decrypt(purpose, blob: bytes, aad: str) -> bytes`; `blob_version(blob) -> int`, `new_dek() -> bytes`, `wrap_key(kek, dek) -> bytes`, `unwrap_key(kek, wrapped) -> bytes`, `normalize_for_index(value) -> str`, `blind_index(key, purpose, value) -> bytes`, `keyed_hash(key, label, value) -> bytes`.
  - `app.core.keystore`: `ensure_keys(conn, kek)`, `load_keyring(conn, kek) -> Keyring`, `get_keyring() -> Keyring` (60 s kesh), `invalidate_keyring()`, `rotate(conn, kek, purpose) -> int`, `rewrap_all(conn, old_kek, new_kek) -> int`, `encrypt(purpose, data, aad) -> bytes`, `decrypt(purpose, blob, aad) -> bytes` (versiya topilmasa keshni yangilab qayta urinadi), `encrypt_str`, `decrypt_str`, `pepper() -> bytes`.
  - `app.bootstrap.bootstrap_runtime() -> None`.

- [ ] **Step 1: 0002 migratsiyasi**

`backend/migrations/versions/0002_crypto_keys.py`:
```python
"""shifrlash kalitlari (DEK, KEK bilan o'ralgan)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-24
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE core.crypto_keys (
          id bigserial PRIMARY KEY,
          purpose text NOT NULL
            CHECK (purpose IN ('pii', 'bank', 'mfa', 'integration_creds', 'audit_meta')),
          version integer NOT NULL CHECK (version > 0),
          wrapped_key bytea NOT NULL,
          status text NOT NULL CHECK (status IN ('active', 'decrypt_only', 'retired')),
          created_at timestamptz NOT NULL DEFAULT now(),
          retired_at timestamptz,
          UNIQUE (purpose, version)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX crypto_keys_one_active ON core.crypto_keys (purpose) "
        "WHERE status = 'active'"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON core.crypto_keys TO ugk_app")
    op.execute("GRANT SELECT ON core.crypto_keys TO ugk_etl")
    op.execute("GRANT USAGE ON SEQUENCE core.crypto_keys_id_seq TO ugk_app")


def downgrade() -> None:
    op.execute("DROP TABLE core.crypto_keys")
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_crypto.py`:
```python
import os

import pytest

from app.core.crypto import (
    CryptoError,
    Keyring,
    Purpose,
    blind_index,
    blob_version,
    keyed_hash,
    new_dek,
    unwrap_key,
    wrap_key,
)


@pytest.fixture
def ring() -> Keyring:
    return Keyring(
        keys={(Purpose.PII, 1): os.urandom(32), (Purpose.PII, 2): os.urandom(32)},
        active={Purpose.PII: 2},
    )


def test_roundtrip_uses_active_version(ring: Keyring) -> None:
    blob = ring.encrypt(Purpose.PII, b"305123456", "core.t.c:1")
    assert blob[0] == 1
    assert blob_version(blob) == 2
    assert ring.decrypt(Purpose.PII, blob, "core.t.c:1") == b"305123456"


def test_same_plaintext_gives_different_ciphertexts(ring: Keyring) -> None:
    assert ring.encrypt(Purpose.PII, b"x", "a") != ring.encrypt(Purpose.PII, b"x", "a")


def test_wrong_aad_is_rejected(ring: Keyring) -> None:
    blob = ring.encrypt(Purpose.PII, b"secret", "core.t.c:1")
    with pytest.raises(CryptoError) as exc:
        ring.decrypt(Purpose.PII, blob, "core.t.c:2")
    assert exc.value.reason == "integrity"


def test_wrong_purpose_is_rejected(ring: Keyring) -> None:
    blob = ring.encrypt(Purpose.PII, b"secret", "a")
    other = Keyring(keys={(Purpose.BANK, 2): ring.keys[(Purpose.PII, 2)]}, active={})
    with pytest.raises(CryptoError):
        other.decrypt(Purpose.BANK, blob, "a")


def test_tampered_byte_is_rejected(ring: Keyring) -> None:
    blob = bytearray(ring.encrypt(Purpose.PII, b"secret", "a"))
    blob[-1] ^= 0x01
    with pytest.raises(CryptoError) as exc:
        ring.decrypt(Purpose.PII, bytes(blob), "a")
    assert exc.value.reason == "integrity"


def test_unknown_version_and_bad_format(ring: Keyring) -> None:
    blob = bytearray(ring.encrypt(Purpose.PII, b"s", "a"))
    blob[1:3] = (9).to_bytes(2, "big")
    with pytest.raises(CryptoError) as exc:
        ring.decrypt(Purpose.PII, bytes(blob), "a")
    assert exc.value.reason == "unknown_key_version"
    with pytest.raises(CryptoError) as exc2:
        ring.decrypt(Purpose.PII, b"\x02" + bytes(40), "a")
    assert exc2.value.reason == "bad_format"


def test_no_active_key() -> None:
    with pytest.raises(CryptoError) as exc:
        Keyring(keys={}, active={}).encrypt(Purpose.MFA, b"x", "a")
    assert exc.value.reason == "no_active_key"


def test_key_wrap_roundtrip_and_wrong_kek() -> None:
    kek, dek = os.urandom(32), new_dek()
    wrapped = wrap_key(kek, dek)
    assert unwrap_key(kek, wrapped) == dek
    with pytest.raises(CryptoError) as exc:
        unwrap_key(os.urandom(32), wrapped)
    assert exc.value.reason == "unwrap_failed"


def test_blind_index_normalizes_and_separates_purposes() -> None:
    key = os.urandom(32)
    assert blind_index(key, "inn", " 305 123 456 ") == blind_index(key, "inn", "305123456")
    assert blind_index(key, "inn", "ABC") == blind_index(key, "inn", "abc")
    assert blind_index(key, "inn", "1") != blind_index(key, "account", "1")
    assert len(blind_index(key, "inn", "1")) == 32


def test_keyed_hash_depends_on_label() -> None:
    key = os.urandom(32)
    assert keyed_hash(key, "session", "t") != keyed_hash(key, "mfa", "t")
```

`backend/tests/test_keystore.py`:
```python
import pytest
from sqlalchemy import text

from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose, blob_version
from app.core.db import get_engine


def _kek() -> bytes:
    return get_settings().key_bytes("master_kek")


def test_ensure_keys_creates_one_active_key_per_purpose() -> None:
    with get_engine("app").begin() as conn:
        keystore.ensure_keys(conn, _kek())
        keystore.ensure_keys(conn, _kek())
        rows = conn.execute(
            text("SELECT purpose, count(*) FROM core.crypto_keys WHERE status='active' GROUP BY 1")
        ).all()
    assert {p for p, _ in rows} == {p.value for p in Purpose}
    assert all(n == 1 for _, n in rows)


def test_encrypt_decrypt_helpers() -> None:
    blob = keystore.encrypt_str(Purpose.PII, "10.0.0.1", "core.x.ip:1")
    assert keystore.decrypt_str(Purpose.PII, blob, "core.x.ip:1") == "10.0.0.1"


def test_rotate_keeps_old_versions_decryptable() -> None:
    old_blob = keystore.encrypt(Purpose.BANK, b"20208000900100001001", "core.b.a:1")
    with get_engine("app").begin() as conn:
        new_version = keystore.rotate(conn, _kek(), Purpose.BANK)
    keystore.invalidate_keyring()
    new_blob = keystore.encrypt(Purpose.BANK, b"x", "core.b.a:2")
    assert blob_version(new_blob) == new_version == blob_version(old_blob) + 1
    assert keystore.decrypt(Purpose.BANK, old_blob, "core.b.a:1") == b"20208000900100001001"


def test_decrypt_refreshes_stale_cache() -> None:
    stale = keystore.get_keyring()  # boshqa worker'dagi eski kesh
    with get_engine("app").begin() as conn:
        keystore.rotate(conn, _kek(), Purpose.INTEGRATION)
        fresh = keystore.load_keyring(conn, _kek())
    blob = fresh.encrypt(Purpose.INTEGRATION, b"1c-password", "core.i.p:1")
    assert keystore.get_keyring() is stale
    assert keystore.decrypt(Purpose.INTEGRATION, blob, "core.i.p:1") == b"1c-password"


def test_rewrap_all_with_new_kek_and_back() -> None:
    import os

    new_kek = os.urandom(32)
    blob = keystore.encrypt(Purpose.PII, b"v", "a")
    with get_engine("app").begin() as conn:
        count = keystore.rewrap_all(conn, _kek(), new_kek)
        assert count >= len(Purpose)
        ring = keystore.load_keyring(conn, new_kek)
        assert ring.decrypt(Purpose.PII, blob, "a") == b"v"
        keystore.rewrap_all(conn, new_kek, _kek())
    keystore.invalidate_keyring()
    assert keystore.decrypt(Purpose.PII, blob, "a") == b"v"


def test_pepper_is_32_bytes() -> None:
    assert len(keystore.pepper()) == 32


def test_etl_role_cannot_modify_keys() -> None:
    from sqlalchemy.exc import ProgrammingError

    with get_engine("etl").begin() as conn, pytest.raises(ProgrammingError):
        conn.execute(text("UPDATE core.crypto_keys SET status = 'retired'"))
```

`backend/tests/conftest.py` — `_database` fixture'ini quyidagicha o'zgartiring (import'lar bilan):
```python
from app.bootstrap import bootstrap_runtime
from app.core import keystore
```
```python
@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    _reset_core()
    keystore.invalidate_keyring()
    bootstrap_runtime()
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_crypto.py tests/test_keystore.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.crypto'`.

- [ ] **Step 4: Implementatsiya**

`backend/app/core/crypto.py`:
```python
"""AES-256-GCM ustun shifrlash, envelope kalitlar, blind index (spec 3.5).

Shifrmatn: 0x01 | key_version (2B) | nonce (12B) | ciphertext | tag (16B).
AAD maqsad va joyni bog'laydi: shifrmatnni boshqa ustun/qatorga ko'chirib bo'lmaydi.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import InvalidUnwrap, aes_key_unwrap, aes_key_wrap

FORMAT_V1 = 1
KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
HEADER_BYTES = 1 + 2 + NONCE_BYTES


class Purpose(StrEnum):
    PII = "pii"
    BANK = "bank"
    MFA = "mfa"
    INTEGRATION = "integration_creds"
    AUDIT = "audit_meta"


class CryptoError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _aad(purpose: str, aad: str) -> bytes:
    return f"ugk|{purpose}|{aad}".encode()


def blob_version(blob: bytes) -> int:
    return int.from_bytes(blob[1:3], "big")


@dataclass(frozen=True, slots=True)
class Keyring:
    keys: Mapping[tuple[str, int], bytes]
    active: Mapping[str, int]

    def encrypt(self, purpose: Purpose, plaintext: bytes, aad: str) -> bytes:
        version = self.active.get(purpose)
        if version is None:
            raise CryptoError("no_active_key")
        nonce = os.urandom(NONCE_BYTES)
        sealed = AESGCM(self.keys[(purpose, version)]).encrypt(nonce, plaintext, _aad(purpose, aad))
        return bytes([FORMAT_V1]) + version.to_bytes(2, "big") + nonce + sealed

    def decrypt(self, purpose: Purpose, blob: bytes, aad: str) -> bytes:
        if len(blob) < HEADER_BYTES + TAG_BYTES or blob[0] != FORMAT_V1:
            raise CryptoError("bad_format")
        key = self.keys.get((purpose, blob_version(blob)))
        if key is None:
            raise CryptoError("unknown_key_version")
        try:
            return AESGCM(key).decrypt(blob[3:HEADER_BYTES], blob[HEADER_BYTES:], _aad(purpose, aad))
        except InvalidTag as exc:
            raise CryptoError("integrity") from exc


def new_dek() -> bytes:
    return os.urandom(KEY_BYTES)


def wrap_key(kek: bytes, dek: bytes) -> bytes:
    """RFC 3394 AES Key Wrap."""
    return aes_key_wrap(kek, dek)


def unwrap_key(kek: bytes, wrapped: bytes) -> bytes:
    try:
        return aes_key_unwrap(kek, wrapped)
    except InvalidUnwrap as exc:
        raise CryptoError("unwrap_failed") from exc


def normalize_for_index(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def blind_index(key: bytes, purpose: str, value: str) -> bytes:
    """Shifrlangan maydon bo'yicha aniq qidiruv uchun HMAC-SHA256."""
    message = f"{purpose}|{normalize_for_index(value)}".encode()
    return hmac.new(key, message, hashlib.sha256).digest()


def keyed_hash(key: bytes, label: str, value: str) -> bytes:
    return hmac.new(key, f"{label}|{value}".encode(), hashlib.sha256).digest()
```

`backend/app/core/keystore.py`:
```python
"""DEK'lar bazada KEK bilan o'ralgan holda turadi; jarayonda 60 s keshlanadi."""

from __future__ import annotations

import threading
import time
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.crypto import CryptoError, Keyring, Purpose, new_dek, unwrap_key, wrap_key
from app.core.db import get_engine

CACHE_TTL_SECONDS = 60.0
_lock = threading.Lock()
_cache: tuple[Keyring, float] | None = None


def ensure_keys(conn: Connection, kek: bytes) -> None:
    """Har maqsad uchun kalit bo'lmasa, 1-versiyani yaratadi (idempotent)."""
    for purpose in Purpose:
        conn.execute(
            text(
                "INSERT INTO core.crypto_keys (purpose, version, wrapped_key, status) "
                "SELECT :p, 1, :w, 'active' "
                "WHERE NOT EXISTS (SELECT 1 FROM core.crypto_keys WHERE purpose = :p) "
                "ON CONFLICT DO NOTHING"
            ),
            {"p": purpose.value, "w": wrap_key(kek, new_dek())},
        )


def load_keyring(conn: Connection, kek: bytes) -> Keyring:
    rows = conn.execute(
        text(
            "SELECT purpose, version, wrapped_key, status FROM core.crypto_keys "
            "WHERE status IN ('active', 'decrypt_only')"
        )
    ).all()
    keys: dict[tuple[str, int], bytes] = {}
    active: dict[str, int] = {}
    for purpose, version, wrapped, status in rows:
        keys[(purpose, version)] = unwrap_key(kek, bytes(wrapped))
        if status == "active":
            active[purpose] = version
    missing = [p.value for p in Purpose if p.value not in active]
    if missing:
        raise CryptoError(f"no_active_key:{','.join(missing)}")
    return Keyring(keys=keys, active=active)


def get_keyring() -> Keyring:
    global _cache
    now = time.monotonic()
    with _lock:
        if _cache is not None and now - _cache[1] < CACHE_TTL_SECONDS:
            return _cache[0]
        kek = get_settings().key_bytes("master_kek")
        with get_engine("app").connect() as conn:
            ring = load_keyring(conn, kek)
        _cache = (ring, now)
        return ring


def invalidate_keyring() -> None:
    global _cache
    with _lock:
        _cache = None


def rotate(conn: Connection, kek: bytes, purpose: Purpose) -> int:
    """Yangi faol versiya; eskisi faqat ochish uchun qoladi."""
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_key_rotate'))"))
    current = conn.execute(
        text("SELECT coalesce(max(version), 0) FROM core.crypto_keys WHERE purpose = :p"),
        {"p": purpose.value},
    ).scalar_one()
    conn.execute(
        text(
            "UPDATE core.crypto_keys SET status = 'decrypt_only' "
            "WHERE purpose = :p AND status = 'active'"
        ),
        {"p": purpose.value},
    )
    new_version = int(current) + 1
    conn.execute(
        text(
            "INSERT INTO core.crypto_keys (purpose, version, wrapped_key, status) "
            "VALUES (:p, :v, :w, 'active')"
        ),
        {"p": purpose.value, "v": new_version, "w": wrap_key(kek, new_dek())},
    )
    return new_version


def rewrap_all(conn: Connection, old_kek: bytes, new_kek: bytes) -> int:
    """KEK rotatsiyasi: barcha tirik DEK'larni yangi KEK bilan qayta o'raydi."""
    rows = conn.execute(
        text("SELECT id, wrapped_key FROM core.crypto_keys WHERE status <> 'retired' FOR UPDATE")
    ).all()
    for key_id, wrapped in rows:
        dek = unwrap_key(old_kek, bytes(wrapped))
        conn.execute(
            text("UPDATE core.crypto_keys SET wrapped_key = :w WHERE id = :id"),
            {"w": wrap_key(new_kek, dek), "id": key_id},
        )
    return len(rows)


def encrypt(purpose: Purpose, plaintext: bytes, aad: str) -> bytes:
    return get_keyring().encrypt(purpose, plaintext, aad)


def decrypt(purpose: Purpose, blob: bytes, aad: str) -> bytes:
    try:
        return get_keyring().decrypt(purpose, blob, aad)
    except CryptoError as exc:
        if exc.reason != "unknown_key_version":
            raise
    # Boshqa worker kalitni aylantirgan bo'lishi mumkin — keshni yangilab qayta urinamiz.
    invalidate_keyring()
    return get_keyring().decrypt(purpose, blob, aad)


def encrypt_str(purpose: Purpose, value: str, aad: str) -> bytes:
    return encrypt(purpose, value.encode("utf-8"), aad)


def decrypt_str(purpose: Purpose, blob: bytes, aad: str) -> str:
    return decrypt(purpose, bytes(blob), aad).decode("utf-8")


@lru_cache(maxsize=1)
def pepper() -> bytes:
    """Sessiya/challenge tokenlari va zaxira kodlar HMAC'i uchun kalit."""
    return get_settings().key_bytes("session_pepper")
```

`backend/app/bootstrap.py`:
```python
"""Ishga tushishdagi idempotent tayyorgarlik. Bir nechta worker parallel chaqirsa ham xavfsiz."""

from __future__ import annotations

from sqlalchemy import text

from app.core import keystore
from app.core.config import get_settings
from app.core.db import get_engine


def bootstrap_runtime() -> None:
    kek = get_settings().key_bytes("master_kek")
    with get_engine("app").begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_bootstrap'))"))
        keystore.ensure_keys(conn, kek)
    keystore.invalidate_keyring()
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(crypto): AES-256-GCM envelope shifrlash, DEK ombori, rotatsiya va rewrap"
```

---

### Task 4: Xatolar, loglash (maskalash), middleware'lar, lifespan

**Files:**
- Create: `backend/app/core/errors.py`, `backend/app/core/logging.py`, `backend/app/core/middleware.py`, `backend/app/core/request_meta.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_errors_middleware.py`, `backend/tests/test_logging.py`

**Interfaces:**
- Produces:
  - `app.core.errors`: `AppError(code=None, *, status_code=None, headers=None, **params)`, `AuthError` (401, `unauthenticated`), `ForbiddenError` (403, `forbidden`), `PasswordChangeRequired` (403), `ScopeViolationError` (403, `scope_violation`), `NotFoundError` (404), `ConflictError` (409, `conflict`), `ValidationFailed` (422, `validation_failed`), `RateLimitedError(retry_after: int)` (429), `MESSAGES: dict[str, str]`, `register_error_handlers(app)`.
  - `app.core.logging`: `configure_logging(level=logging.INFO)`, `get_logger(name)`, `mask(value, key=None)`, `MASK = "***"`.
  - `app.core.middleware`: `RequestContextMiddleware`, `SecurityHeadersMiddleware(app, *, hsts: bool)`, `BodySizeLimitMiddleware(app, *, max_bytes: int)`, `MAX_BODY_BYTES = 1_048_576`, `SECURITY_HEADERS`.
  - `app.core.request_meta`: `ClientMeta(ip, ua, request_id)`, `client_meta(request) -> ClientMeta`, `Meta = Annotated[ClientMeta, Depends(client_meta)]`.
  - `app.main`: `lifespan` (config tekshiruvi + `bootstrap_runtime`), `create_app()`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_logging.py`:
```python
from app.core.logging import MASK, mask


def test_mask_hides_sensitive_keys_recursively() -> None:
    data = {
        "password": "p",
        "username": "ali",
        "nested": {"new_password": "n", "session_token": "t", "ok": 1},
        "items": [{"totp_secret": "s"}, {"inn": "305"}],
        "status_code": 200,
        "code": "123456",
    }
    assert mask(data) == {
        "password": MASK,
        "username": "ali",
        "nested": {"new_password": MASK, "session_token": MASK, "ok": 1},
        "items": [{"totp_secret": MASK}, {"inn": MASK}],
        "status_code": 200,
        "code": MASK,
    }


def test_mask_leaves_scalars() -> None:
    assert mask("plain") == "plain"
    assert mask(5, "user_id") == 5
```

`backend/tests/test_errors_middleware.py`:
```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import ConflictError, RateLimitedError
from app.main import create_app


class Body(BaseModel):
    secret_value: str
    amount: int


def _app() -> FastAPI:
    app = create_app()

    @app.get("/api/v1/_t/conflict")
    def conflict() -> None:
        raise ConflictError("username_taken")

    @app.get("/api/v1/_t/limited")
    def limited() -> None:
        raise RateLimitedError(retry_after=42)

    @app.get("/api/v1/_t/boom")
    def boom() -> None:
        raise RuntimeError("DB password is hunter2")

    @app.post("/api/v1/_t/echo")
    def echo(body: Body) -> dict[str, int]:
        return {"amount": body.amount}

    return app


@pytest.fixture
def client() -> TestClient:
    with TestClient(_app(), base_url="https://testserver", raise_server_exceptions=False) as c:
        yield c


def test_app_error_format(client: TestClient) -> None:
    r = client.get("/api/v1/_t/conflict")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "username_taken"
    assert err["message"] == "Логин уже занят"
    assert err["request_id"] == r.headers["X-Request-ID"]


def test_rate_limited_sets_retry_after(client: TestClient) -> None:
    r = client.get("/api/v1/_t/limited")
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "42"
    assert r.json()["error"]["params"] == {"retry_after": 42}


def test_unhandled_error_hides_details(client: TestClient) -> None:
    r = client.get("/api/v1/_t/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in r.text


def test_validation_error_does_not_echo_input(client: TestClient) -> None:
    r = client.post("/api/v1/_t/echo", json={"secret_value": "TOPSECRET", "amount": "abc"})
    assert r.status_code == 422
    assert r.json()["error"]["params"] == {"fields": ["amount"]}
    assert "TOPSECRET" not in r.text


def test_unknown_route_is_formatted_404(client: TestClient) -> None:
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_security_headers_present(client: TestClient) -> None:
    r = client.get("/api/v1/healthz")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["Strict-Transport-Security"].startswith("max-age=")
    assert len(r.headers["X-Request-ID"]) == 32


def test_body_limit_by_content_length(client: TestClient) -> None:
    r = client.post("/api/v1/_t/echo", content=b"x" * 1_100_000,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_lifespan_refuses_bad_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main as main_module

    monkeypatch.setattr(main_module, "get_settings", lambda: Settings(env="test", master_kek="bad"))
    with pytest.raises(Exception, match="master_kek"), TestClient(main_module.create_app()):
        pass
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_logging.py tests/test_errors_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.logging'`.

- [ ] **Step 3: Implementatsiya**

`backend/app/core/logging.py`:
```python
"""Strukturali JSON loglar; sezgir kalitlar avtomatik maskalanadi (spec 3.7)."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

MASK = "***"
_SENSITIVE_TOKENS = frozenset(
    {
        "password", "passwd", "pwd", "token", "secret", "cookie", "authorization",
        "totp", "otp", "kek", "pepper", "csrf", "inn", "account",
    }
)
_SENSITIVE_KEYS = frozenset({"code", "mfa_code", "backup_code"})
_SPLIT = re.compile(r"[_\-.\s]+")
_RESERVED = frozenset({"event", "level", "timestamp", "logger"})


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return lowered in _SENSITIVE_KEYS or any(t in _SENSITIVE_TOKENS for t in _SPLIT.split(lowered))


def mask(value: Any, key: str | None = None) -> Any:
    if key is not None and _is_sensitive(key):
        return MASK
    if isinstance(value, dict):
        return {str(k): mask(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [mask(v) for v in value]
    return value


def _mask_processor(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {k: (v if k in _RESERVED else mask(v, k)) for k, v in event_dict.items()}


def configure_logging(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _mask_processor,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
```

`backend/app/core/request_meta.py`:
```python
"""So'rov haqidagi audit uchun kerakli ma'lumotlar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

UA_MAX = 512


@dataclass(frozen=True, slots=True)
class ClientMeta:
    ip: str | None
    ua: str | None
    request_id: str | None


def client_meta(request: Request) -> ClientMeta:
    ua = request.headers.get("user-agent")
    return ClientMeta(
        ip=request.client.host if request.client else None,
        ua=ua[:UA_MAX] if ua else None,
        request_id=getattr(request.state, "request_id", None),
    )


Meta = Annotated[ClientMeta, Depends(client_meta)]
```

`backend/app/core/errors.py`:
```python
"""Xatolar daraxti va yagona javob formati: {"error": {code, message, request_id, params?}}.

Ichki tafsilotlar (stack trace, SQL, kiritilgan qiymatlar) hech qachon javobga chiqmaydi.
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
    "username_taken": "Логин уже занят",
    "code_taken": "Код уже используется",
    "last_admin": "Нельзя оставить систему без администратора",
    "admin_role_protected": "У роли администратора нельзя отнять права администрирования",
    "cannot_modify_self": "Это действие нельзя выполнить со своей учётной записью",
    "validation_failed": "Проверьте введённые данные",
    "invalid_current_password": "Текущий пароль указан неверно",
    "password_policy": "Пароль не соответствует политике",
    "unknown_permission": "Неизвестное право доступа",
    "rate_limited": "Слишком много запросов, повторите позже",
    "payload_too_large": "Слишком большой запрос",
    "method_not_allowed": "Метод не поддерживается",
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


class PasswordChangeRequired(ForbiddenError):
    code = "password_change_required"


class ScopeViolationError(ForbiddenError):
    code = "scope_violation"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailed(AppError):
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
        from app.audit.service import AuditAction, log_event  # sikl import'dan qochish
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
```

`ScopeViolationError` handler'i `app.audit.service` ni ishlatadi, u Task 6 da paydo bo'ladi. Task 4–5 da bu handler chaqirilmaydi (import funksiya ichida), shuning uchun yiqilmaydi.

`backend/app/core/middleware.py`:
```python
"""Sof ASGI middleware'lar: request-id + access log, xavfsizlik sarlavhalari, tana limiti."""

from __future__ import annotations

import time
import uuid
from typing import Final

import structlog
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import MESSAGES
from app.core.logging import get_logger

MAX_BODY_BYTES: Final = 1_048_576
SECURITY_HEADERS: Final[dict[str, str]] = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
        "microphone=(), payment=(), usb=()"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
HSTS: Final = "max-age=63072000; includeSubDomains"

access_log = get_logger("ugekazna.access")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        started = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            access_log.info(
                "http",
                method=scope["method"],
                path=scope["path"],
                status=status["code"],
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                user_id=state.get("user_id"),
            )
            structlog.contextvars.unbind_contextvars("request_id")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                headers.setdefault("Cache-Control", "no-store")
                if self.hsts:
                    headers.setdefault("Strict-Transport-Security", HSTS)
            await send(message)

        await self.app(scope, receive, send_wrapper)


class _TooLargeError(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            await self._reject(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _TooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _TooLargeError:
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        body = {
            "error": {
                "code": "payload_too_large",
                "message": MESSAGES["payload_too_large"],
                "request_id": scope.get("state", {}).get("request_id"),
            }
        }
        await JSONResponse(body, status_code=413)(scope, receive, send)
```

`backend/app/main.py` — to'liq almashtiring:
```python
"""FastAPI ilovasi."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from app import __version__
from app.bootstrap import bootstrap_runtime
from app.core.config import ConfigError, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    MAX_BODY_BYTES,
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.health.router import router as health_router

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    problems = get_settings().problems()
    if problems:
        raise ConfigError("; ".join(problems))
    await run_in_threadpool(bootstrap_runtime)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title="UGEKAZNA API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    register_error_handlers(app)
    # Oxirgi qo'shilgan — eng tashqi: RequestContext birinchi ishlaydi.
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.base_url.startswith("https://"))
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router, prefix=API_PREFIX)
    return app


app = create_app()
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(core): xato formati, maskalangan JSON loglar, xavfsizlik middleware'lari, lifespan"
```

---

### Task 5: Identifikatsiya sxemasi, rollar va ruxsatlar seed'i

**Files:**
- Create: `backend/migrations/versions/0003_identity.py`, `backend/app/core/models.py`, `backend/app/auth/__init__.py`, `backend/app/auth/models.py`, `backend/app/auth/permissions.py`, `backend/app/auth/seed.py`
- Modify: `backend/app/bootstrap.py`
- Test: `backend/tests/test_identity_seed.py`

**Interfaces:**
- Consumes: `new_session`, `get_engine`.
- Produces:
  - `app.core.models.Base` (`MetaData(schema="core")`).
  - `app.auth.models`: `Permission(code, description)`, `Role(id, code, name, scope_all, is_system)`, `RolePermission(role_id, permission_code)`, `Position(id, code, name, role_id, is_active)`, `PositionBranch(position_id, branch_id)`, `User(id, username, full_name, position_id, password_hash, password_changed_at, must_change_password, is_active, failed_logins, locked_until, totp_secret_enc, totp_enabled, totp_last_step, last_login_at, created_at, updated_at)`, `PasswordHistory(id, user_id, password_hash, created_at)`, `BackupCode(id, user_id, code_hmac, used_at)`, `UserSession(id: uuid, user_id, token_hmac, created_at, last_seen_at, idle_expires_at, absolute_expires_at, revoked_at, revoke_reason, ip_enc, ua_summary)`, `MfaChallenge(token_hmac, user_id, kind, created_at, expires_at, attempts, used_at)`.
  - `app.auth.permissions`: `Section` (StrEnum: obzor, kazna, kredity, finmodel, zakupki, sklad, proizvodstvo, investicii, kadry), `SECTION_TITLES`, `section_perm(s) -> str` (`"section:<id>:view"`), `Perm` (StrEnum: `EXPORT_CSV="export:csv"`, `EXPORT_XLSX="export:xlsx"`, `ADMIN_USERS="admin:users"`, `ADMIN_ROLES="admin:roles"`, `ADMIN_SETTINGS="admin:settings"`, `ADMIN_ETL="admin:etl"`, `ADMIN_KEYS="admin:keys"`, `AUDIT_READ="audit:read"`), `PERMISSIONS: dict[str, str]`, `RoleSeed(code, name, scope_all, permissions)`, `ROLE_SEEDS`, `ADMIN_ROLE = "admin"`, `ADMIN_GUARANTEED`.
  - `app.auth.seed.sync_reference(db: Session) -> None`.

- [ ] **Step 1: 0003 migratsiyasi**

`backend/migrations/versions/0003_identity.py`:
```python
"""foydalanuvchilar, lavozimlar, rollar, sessiyalar, 2FA

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-24
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE core.permissions (
      code varchar(64) PRIMARY KEY,
      description varchar(300) NOT NULL
    )
    """,
    """
    CREATE TABLE core.roles (
      id serial PRIMARY KEY,
      code varchar(64) NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]{1,63}$'),
      name varchar(200) NOT NULL,
      scope_all boolean NOT NULL,
      is_system boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE core.role_permissions (
      role_id integer NOT NULL REFERENCES core.roles(id) ON DELETE CASCADE,
      permission_code varchar(64) NOT NULL REFERENCES core.permissions(code) ON DELETE CASCADE,
      PRIMARY KEY (role_id, permission_code)
    )
    """,
    """
    CREATE TABLE core.positions (
      id serial PRIMARY KEY,
      code varchar(64) NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]{1,63}$'),
      name varchar(200) NOT NULL,
      role_id integer NOT NULL REFERENCES core.roles(id),
      is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX positions_role_idx ON core.positions (role_id)",
    """
    CREATE TABLE core.position_branches (
      position_id integer NOT NULL REFERENCES core.positions(id) ON DELETE CASCADE,
      branch_id integer NOT NULL CHECK (branch_id > 0),
      PRIMARY KEY (position_id, branch_id)
    )
    """,
    """
    CREATE TABLE core.users (
      id bigserial PRIMARY KEY,
      username varchar(64) NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9._-]{3,64}$'),
      full_name varchar(200) NOT NULL,
      position_id integer NOT NULL REFERENCES core.positions(id),
      password_hash text NOT NULL,
      password_changed_at timestamptz NOT NULL DEFAULT now(),
      must_change_password boolean NOT NULL DEFAULT true,
      is_active boolean NOT NULL DEFAULT true,
      failed_logins integer NOT NULL DEFAULT 0,
      locked_until timestamptz,
      totp_secret_enc bytea,
      totp_enabled boolean NOT NULL DEFAULT false,
      totp_last_step bigint,
      last_login_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX users_position_idx ON core.users (position_id)",
    """
    CREATE TABLE core.password_history (
      id bigserial PRIMARY KEY,
      user_id bigint NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
      password_hash text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX password_history_user_idx ON core.password_history (user_id, created_at DESC)",
    """
    CREATE TABLE core.backup_codes (
      id bigserial PRIMARY KEY,
      user_id bigint NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
      code_hmac bytea NOT NULL,
      used_at timestamptz
    )
    """,
    "CREATE INDEX backup_codes_user_idx ON core.backup_codes (user_id) WHERE used_at IS NULL",
    """
    CREATE TABLE core.sessions (
      id uuid PRIMARY KEY,
      user_id bigint NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
      token_hmac bytea NOT NULL UNIQUE,
      created_at timestamptz NOT NULL,
      last_seen_at timestamptz NOT NULL,
      idle_expires_at timestamptz NOT NULL,
      absolute_expires_at timestamptz NOT NULL,
      revoked_at timestamptz,
      revoke_reason varchar(32),
      ip_enc bytea,
      ua_summary varchar(80) NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX sessions_user_active_idx ON core.sessions (user_id) WHERE revoked_at IS NULL",
    """
    CREATE TABLE core.mfa_challenges (
      token_hmac bytea PRIMARY KEY,
      user_id bigint NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
      kind varchar(8) NOT NULL CHECK (kind IN ('verify', 'enroll')),
      created_at timestamptz NOT NULL,
      expires_at timestamptz NOT NULL,
      attempts integer NOT NULL DEFAULT 0,
      used_at timestamptz
    )
    """,
    "CREATE INDEX mfa_challenges_expires_idx ON core.mfa_challenges (expires_at)",
    # ── Huquqlar: foydalanuvchilar o'chirilmaydi, faqat bloklanadi ──
    """
    GRANT SELECT, INSERT, UPDATE, DELETE ON core.permissions, core.roles,
      core.role_permissions, core.positions, core.position_branches TO ugk_app
    """,
    "GRANT SELECT, INSERT, UPDATE ON core.users TO ugk_app",
    "GRANT SELECT, INSERT, DELETE ON core.password_history TO ugk_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON core.backup_codes TO ugk_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON core.sessions, core.mfa_challenges TO ugk_app",
    """
    GRANT USAGE ON SEQUENCE core.roles_id_seq, core.positions_id_seq, core.users_id_seq,
      core.password_history_id_seq, core.backup_codes_id_seq TO ugk_app
    """,
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in (
        "mfa_challenges", "sessions", "backup_codes", "password_history", "users",
        "position_branches", "positions", "role_permissions", "roles", "permissions",
    ):
        op.execute(f"DROP TABLE core.{table}")
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_identity_seed.py`:
```python
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.auth.models import Permission, Position, Role, RolePermission
from app.auth.permissions import ADMIN_GUARANTEED, PERMISSIONS, Perm, Section, section_perm
from app.auth.seed import sync_reference
from app.core.db import new_session

S = {s: section_perm(s) for s in Section}
EXPORT = {Perm.EXPORT_CSV.value, Perm.EXPORT_XLSX.value}

# Spec 3.3 / TZ 1-bo'lim jadvali.
EXPECTED = {
    "rukovodstvo": (True, set(S.values()) | EXPORT),
    "nach_otdela": (True, set(S.values()) | EXPORT),
    "spec_kazna": (
        True,
        {S[Section.OBZOR], S[Section.KAZNA], S[Section.KREDITY], S[Section.FINMODEL]} | EXPORT,
    ),
    "economist_filiala": (
        False,
        {S[Section.OBZOR], S[Section.KAZNA], S[Section.PROIZVODSTVO], S[Section.SKLAD],
         S[Section.KADRY]} | EXPORT,
    ),
    "profil_sluzhba": (True, {S[Section.OBZOR]} | EXPORT),
    "admin": (True, set(S.values()) | {p.value for p in Perm}),
    "vnutr_kontrol": (True, {S[Section.OBZOR], Perm.AUDIT_READ.value}),
}


def _role_matrix(db: Session) -> dict[str, tuple[bool, set[str]]]:
    out: dict[str, tuple[bool, set[str]]] = {}
    for role in db.execute(select(Role).where(Role.is_system.is_(True))).scalars():
        perms = set(
            db.execute(
                select(RolePermission.permission_code).where(RolePermission.role_id == role.id)
            ).scalars()
        )
        out[role.code] = (role.scope_all, perms)
    return out


def test_permissions_table_matches_code(db: Session) -> None:
    rows = dict(db.execute(select(Permission.code, Permission.description)).tuples().all())
    assert rows == PERMISSIONS


def test_system_roles_match_spec(db: Session) -> None:
    assert _role_matrix(db) == EXPECTED


def test_each_system_role_has_a_position(db: Session) -> None:
    codes = set(db.execute(select(Position.code)).scalars())
    assert set(EXPECTED) <= codes


def test_sync_is_idempotent_and_restores_admin_guarantees() -> None:
    with new_session() as s:
        admin_id = s.execute(select(Role.id).where(Role.code == "admin")).scalar_one()
        s.execute(
            text("DELETE FROM core.role_permissions WHERE role_id = :r AND permission_code = :p"),
            {"r": admin_id, "p": Perm.ADMIN_USERS.value},
        )
        sync_reference(s)
        sync_reference(s)
        perms = set(
            s.execute(
                select(RolePermission.permission_code).where(RolePermission.role_id == admin_id)
            ).scalars()
        )
        s.commit()
    assert ADMIN_GUARANTEED <= perms


def test_username_format_is_enforced_by_db(db: Session) -> None:
    pos_id = db.execute(select(Position.id).where(Position.code == "admin")).scalar_one()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO core.users (username, full_name, position_id, password_hash) "
                "VALUES ('Bad Name', 'x', :p, 'h')"
            ),
            {"p": pos_id},
        )


def test_app_role_cannot_delete_users(db: Session) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        db.execute(text("DELETE FROM core.users"))
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_identity_seed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'`.

- [ ] **Step 4: Implementatsiya**

`backend/app/auth/__init__.py`: bo'sh fayl.

`backend/app/core/models.py`:
```python
"""ORM asosi: barcha jadvallar `core` sxemasida, vaqt ustunlari timezone-aware."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(schema="core")
    type_annotation_map = {datetime: DateTime(timezone=True)}
```

`backend/app/auth/models.py`:
```python
"""Identifikatsiya jadvallari (migratsiya 0003 bilan bir xil)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class Permission(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(300))


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    scope_all: Mapped[bool]
    is_system: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[int] = mapped_column(
        ForeignKey("core.roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("core.permissions.code", ondelete="CASCADE"), primary_key=True
    )


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role_id: Mapped[int] = mapped_column(ForeignKey("core.roles.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PositionBranch(Base):
    __tablename__ = "position_branches"
    position_id: Mapped[int] = mapped_column(
        ForeignKey("core.positions.id", ondelete="CASCADE"), primary_key=True
    )
    branch_id: Mapped[int] = mapped_column(Integer, primary_key=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    position_id: Mapped[int] = mapped_column(ForeignKey("core.positions.id"))
    password_hash: Mapped[str] = mapped_column(Text)
    password_changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    must_change_password: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None]
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_enabled: Mapped[bool] = mapped_column(default=False)
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    last_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PasswordHistory(Base):
    __tablename__ = "password_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BackupCode(Base):
    __tablename__ = "backup_codes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    code_hmac: Mapped[bytes] = mapped_column(LargeBinary)
    used_at: Mapped[datetime | None]


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    token_hmac: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    created_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    idle_expires_at: Mapped[datetime]
    absolute_expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    revoke_reason: Mapped[str | None] = mapped_column(String(32))
    ip_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    ua_summary: Mapped[str] = mapped_column(String(80), default="")


class MfaChallenge(Base):
    __tablename__ = "mfa_challenges"
    token_hmac: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(default=0)
    used_at: Mapped[datetime | None]
```

`backend/app/auth/permissions.py`:
```python
"""Bo'limlar, ruxsatlar va tizim rollari (spec 3.3, TZ 1-bo'lim).

Kod — ruxsatlar ro'yxatining yagona manbai. Tizim rollari faqat BIRINCHI marta
yaratilganda seed qilinadi, keyin ularni administrator boshqaradi.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Section(StrEnum):
    OBZOR = "obzor"
    KAZNA = "kazna"
    KREDITY = "kredity"
    FINMODEL = "finmodel"
    ZAKUPKI = "zakupki"
    SKLAD = "sklad"
    PROIZVODSTVO = "proizvodstvo"
    INVESTICII = "investicii"
    KADRY = "kadry"


SECTION_TITLES: dict[Section, str] = {
    Section.OBZOR: "Обзор",
    Section.KAZNA: "Казначейство",
    Section.KREDITY: "Кредиты",
    Section.FINMODEL: "Финмодель",
    Section.ZAKUPKI: "Закупки",
    Section.SKLAD: "Склад",
    Section.PROIZVODSTVO: "Производство",
    Section.INVESTICII: "Инвестиции",
    Section.KADRY: "Кадры",
}


def section_perm(section: Section) -> str:
    return f"section:{section.value}:view"


class Perm(StrEnum):
    EXPORT_CSV = "export:csv"
    EXPORT_XLSX = "export:xlsx"
    ADMIN_USERS = "admin:users"
    ADMIN_ROLES = "admin:roles"
    ADMIN_SETTINGS = "admin:settings"
    ADMIN_ETL = "admin:etl"
    ADMIN_KEYS = "admin:keys"
    AUDIT_READ = "audit:read"


_PERM_TITLES: dict[Perm, str] = {
    Perm.EXPORT_CSV: "Выгрузка таблиц в CSV",
    Perm.EXPORT_XLSX: "Выгрузка в Excel (.xlsx)",
    Perm.ADMIN_USERS: "Администрирование: пользователи",
    Perm.ADMIN_ROLES: "Администрирование: должности и роли",
    Perm.ADMIN_SETTINGS: "Администрирование: настройки и пороги",
    Perm.ADMIN_ETL: "Администрирование: загрузки данных",
    Perm.ADMIN_KEYS: "Администрирование: ключи шифрования",
    Perm.AUDIT_READ: "Просмотр журнала аудита",
}

PERMISSIONS: dict[str, str] = {
    **{section_perm(s): f"Раздел «{t}»: просмотр" for s, t in SECTION_TITLES.items()},
    **{p.value: t for p, t in _PERM_TITLES.items()},
}


@dataclass(frozen=True, slots=True)
class RoleSeed:
    code: str
    name: str
    scope_all: bool
    permissions: frozenset[str]


def _sections(*items: Section) -> frozenset[str]:
    return frozenset(section_perm(s) for s in items)


_ALL_SECTIONS = _sections(*Section)
_EXPORT = frozenset({Perm.EXPORT_CSV.value, Perm.EXPORT_XLSX.value})

ADMIN_ROLE = "admin"
ADMIN_GUARANTEED = frozenset({Perm.ADMIN_USERS.value, Perm.ADMIN_ROLES.value})

ROLE_SEEDS: tuple[RoleSeed, ...] = (
    RoleSeed("rukovodstvo", "Руководство", True, _ALL_SECTIONS | _EXPORT),
    RoleSeed(
        "nach_otdela",
        "Начальник отдела финансирования и контроля денежных потоков",
        True,
        _ALL_SECTIONS | _EXPORT,
    ),
    RoleSeed(
        "spec_kazna",
        "Специалист казначейства",
        True,
        _sections(Section.OBZOR, Section.KAZNA, Section.KREDITY, Section.FINMODEL) | _EXPORT,
    ),
    RoleSeed(
        "economist_filiala",
        "Экономист филиала",
        False,
        _sections(Section.OBZOR, Section.KAZNA, Section.PROIZVODSTVO, Section.SKLAD, Section.KADRY)
        | _EXPORT,
    ),
    RoleSeed("profil_sluzhba", "Профильная служба", True, _sections(Section.OBZOR) | _EXPORT),
    RoleSeed(ADMIN_ROLE, "Администратор", True, _ALL_SECTIONS | frozenset(p.value for p in Perm)),
    RoleSeed(
        "vnutr_kontrol",
        "Служба внутреннего контроля",
        True,
        _sections(Section.OBZOR) | {Perm.AUDIT_READ.value},
    ),
)
```

`backend/app/auth/seed.py`:
```python
"""Ruxsatlar va tizim rollarini koddan bazaga sinxronlash (idempotent)."""

from __future__ import annotations

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.auth.models import Permission, Position, Role, RolePermission
from app.auth.permissions import ADMIN_GUARANTEED, ADMIN_ROLE, PERMISSIONS, ROLE_SEEDS


def sync_reference(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_sync_reference'))"))
    for code, description in PERMISSIONS.items():
        db.execute(
            pg_insert(Permission)
            .values(code=code, description=description)
            .on_conflict_do_update(index_elements=[Permission.code], set_={"description": description})
        )
    db.execute(delete(Permission).where(Permission.code.not_in(list(PERMISSIONS))))

    for seed in ROLE_SEEDS:
        role = db.execute(select(Role).where(Role.code == seed.code)).scalar_one_or_none()
        if role is None:
            role = Role(code=seed.code, name=seed.name, scope_all=seed.scope_all, is_system=True)
            db.add(role)
            db.flush()
            for perm in sorted(seed.permissions):
                db.add(RolePermission(role_id=role.id, permission_code=perm))
        if db.execute(select(Position.id).where(Position.code == seed.code)).first() is None:
            db.add(Position(code=seed.code, name=seed.name, role_id=role.id))

    admin_id = db.execute(select(Role.id).where(Role.code == ADMIN_ROLE)).scalar_one()
    for perm in sorted(ADMIN_GUARANTEED):
        db.execute(
            pg_insert(RolePermission)
            .values(role_id=admin_id, permission_code=perm)
            .on_conflict_do_nothing()
        )
    db.flush()
```

`backend/app/bootstrap.py` — to'liq almashtiring:
```python
"""Ishga tushishdagi idempotent tayyorgarlik. Bir nechta worker parallel chaqirsa ham xavfsiz."""

from __future__ import annotations

from sqlalchemy import text

from app.auth.seed import sync_reference
from app.core import keystore
from app.core.config import get_settings
from app.core.db import get_engine, new_session


def bootstrap_runtime() -> None:
    kek = get_settings().key_bytes("master_kek")
    with get_engine("app").begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_bootstrap'))"))
        keystore.ensure_keys(conn, kek)
    keystore.invalidate_keyring()
    with new_session() as db:
        sync_reference(db)
        db.commit()
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(auth): identifikatsiya sxemasi, TZ bo'yicha rollar va ruxsatlar seed'i"
```

---

### Task 6: O'zgarmas audit jurnali (hash-chain, shifrlangan IP/UA, partitsiyalar)

**Files:**
- Create: `backend/migrations/versions/0004_audit.py`, `backend/app/audit/__init__.py`, `backend/app/audit/service.py`
- Modify: `backend/app/bootstrap.py`
- Test: `backend/tests/test_audit_service.py`

**Interfaces:**
- Consumes: `keystore.encrypt_str/decrypt_str`, `Purpose.AUDIT`, `get_engine`, `mask`, `ClientMeta`.
- Produces: `app.audit.service`: `AuditAction` (StrEnum — ro'yxat pastda), `AuditEvent(action, result="ok", user_id=None, object_type=None, object_id=None, details={}, ip=None, ua=None, request_id=None)`, `record(event) -> int`, `log_event(meta, action, *, user_id, result="ok", object_type=None, object_id=None, details=None) -> int`, `ChainReport(ok, checked, first_bad_id)`, `verify_chain(conn) -> ChainReport`, `verify_chain_snapshot() -> ChainReport`, `canonical(row) -> bytes`, `chain_hash(prev, row) -> bytes`, `GENESIS`, `ip_aad(audit_id) -> str`; SQL `core.ensure_audit_partitions(int) -> int`, `core.drop_old_audit_partitions(int) -> int`.

- [ ] **Step 1: 0004 migratsiyasi**

`backend/migrations/versions/0004_audit.py`:
```python
"""audit jurnali: oylik partitsiyalar, hash-chain boshi

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-24
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

STATEMENTS = [
    "CREATE SEQUENCE core.audit_log_id_seq",
    """
    CREATE TABLE core.audit_log (
      id bigint NOT NULL,
      ts timestamptz NOT NULL,
      user_id bigint,
      action varchar(64) NOT NULL,
      result varchar(8) NOT NULL CHECK (result IN ('ok', 'fail', 'denied')),
      object_type varchar(32),
      object_id varchar(64),
      request_id varchar(32),
      details jsonb NOT NULL DEFAULT '{}'::jsonb,
      ip_enc bytea,
      ua_enc bytea,
      prev_hash bytea NOT NULL,
      hash bytea NOT NULL,
      PRIMARY KEY (id, ts)
    ) PARTITION BY RANGE (ts)
    """,
    "CREATE TABLE core.audit_log_default PARTITION OF core.audit_log DEFAULT",
    "CREATE INDEX audit_log_id_idx ON core.audit_log (id)",
    "CREATE INDEX audit_log_ts_idx ON core.audit_log (ts)",
    "CREATE INDEX audit_log_user_ts_idx ON core.audit_log (user_id, ts)",
    "CREATE INDEX audit_log_action_ts_idx ON core.audit_log (action, ts)",
    """
    CREATE TABLE core.audit_head (
      id smallint PRIMARY KEY CHECK (id = 1),
      last_id bigint,
      last_hash bytea NOT NULL
    )
    """,
    "INSERT INTO core.audit_head (id, last_id, last_hash) VALUES (1, NULL, decode(repeat('00', 32), 'hex'))",
    """
    CREATE FUNCTION core.ensure_audit_partitions(months_ahead integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, core AS $$
    DECLARE
      base date := date_trunc('month', now() AT TIME ZONE 'UTC')::date;
      created integer := 0;
      part text;
      start_ts timestamptz;
      end_ts timestamptz;
    BEGIN
      FOR i IN 0..months_ahead LOOP
        part := 'audit_log_' || to_char(base + make_interval(months => i), 'YYYYMM');
        IF to_regclass('core.' || part) IS NULL THEN
          start_ts := (base + make_interval(months => i)) AT TIME ZONE 'UTC';
          end_ts := (base + make_interval(months => i + 1)) AT TIME ZONE 'UTC';
          EXECUTE format(
            'CREATE TABLE core.%I PARTITION OF core.audit_log FOR VALUES FROM (%L) TO (%L)',
            part, start_ts, end_ts);
          created := created + 1;
        END IF;
      END LOOP;
      RETURN created;
    END
    $$
    """,
    """
    CREATE FUNCTION core.drop_old_audit_partitions(keep_months integer) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, core AS $$
    DECLARE
      cutoff date := (date_trunc('month', now() AT TIME ZONE 'UTC')
                      - make_interval(months => keep_months))::date;
      dropped integer := 0;
      r record;
    BEGIN
      FOR r IN
        SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
        WHERE i.inhparent = 'core.audit_log'::regclass AND c.relname ~ '^audit_log_[0-9]{6}$'
      LOOP
        IF to_date(substr(r.relname, 11), 'YYYYMM') < cutoff THEN
          EXECUTE format('DROP TABLE core.%I', r.relname);
          dropped := dropped + 1;
        END IF;
      END LOOP;
      RETURN dropped;
    END
    $$
    """,
    "REVOKE ALL ON FUNCTION core.ensure_audit_partitions(integer) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION core.drop_old_audit_partitions(integer) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION core.ensure_audit_partitions(integer) TO ugk_app, ugk_etl",
    "GRANT EXECUTE ON FUNCTION core.drop_old_audit_partitions(integer) TO ugk_etl",
    "SELECT core.ensure_audit_partitions(3)",
    # Faqat qo'shish: UPDATE/DELETE hech kimga berilmaydi.
    "GRANT SELECT, INSERT ON core.audit_log TO ugk_app, ugk_etl",
    "GRANT SELECT, UPDATE ON core.audit_head TO ugk_app, ugk_etl",
    "GRANT USAGE ON SEQUENCE core.audit_log_id_seq TO ugk_app, ugk_etl",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP FUNCTION core.drop_old_audit_partitions(integer)")
    op.execute("DROP FUNCTION core.ensure_audit_partitions(integer)")
    op.execute("DROP TABLE core.audit_head")
    op.execute("DROP TABLE core.audit_log")
    op.execute("DROP SEQUENCE core.audit_log_id_seq")
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_audit_service.py`:
```python
import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.audit.service import AuditAction, AuditEvent, ip_aad, record, verify_chain_snapshot
from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session


def _row(audit_id: int) -> dict[str, object]:
    with get_engine("app").connect() as conn:
        return dict(
            conn.execute(
                text("SELECT *, tableoid::regclass::text AS part FROM core.audit_log WHERE id = :i"),
                {"i": audit_id},
            ).mappings().one()
        )


def test_record_stores_encrypted_ip_and_masked_details() -> None:
    audit_id = record(
        AuditEvent(
            action=AuditAction.LOGIN_FAIL,
            result="fail",
            ip="192.168.10.5",
            ua="Mozilla/5.0",
            request_id="r1",
            details={"username": "ali", "password": "hunter2"},
        )
    )
    row = _row(audit_id)
    assert b"192.168.10.5" not in bytes(row["ip_enc"])  # type: ignore[arg-type]
    assert keystore.decrypt_str(Purpose.AUDIT, row["ip_enc"], ip_aad(audit_id)) == "192.168.10.5"  # type: ignore[arg-type]
    assert row["details"] == {"username": "ali", "password": "***"}
    month = datetime.now(UTC).strftime("%Y%m")
    assert row["part"] == f"core.audit_log_{month}"


def test_chain_is_valid_after_records() -> None:
    for _ in range(3):
        record(AuditEvent(action=AuditAction.LOGOUT, user_id=1))
    report = verify_chain_snapshot()
    assert report.ok
    assert report.checked >= 3


def test_concurrent_records_keep_chain_valid() -> None:
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(10):
                record(AuditEvent(action=AuditAction.LOGOUT))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert verify_chain_snapshot().ok


def test_tampering_is_detected_and_then_repaired() -> None:
    victim = record(AuditEvent(action=AuditAction.USER_CREATED, details={"username": "x"}))
    record(AuditEvent(action=AuditAction.LOGOUT))
    with get_engine("migrator").begin() as conn:
        original = conn.execute(
            text("SELECT details FROM core.audit_log WHERE id = :i"), {"i": victim}
        ).scalar_one()
        conn.execute(
            text("""UPDATE core.audit_log SET details = '{"username": "y"}' WHERE id = :i"""),
            {"i": victim},
        )
    try:
        report = verify_chain_snapshot()
        assert not report.ok
        assert report.first_bad_id == victim
    finally:
        with get_engine("migrator").begin() as conn:
            conn.execute(
                text("UPDATE core.audit_log SET details = CAST(:d AS jsonb) WHERE id = :i"),
                {"d": __import__("json").dumps(original), "i": victim},
            )
    assert verify_chain_snapshot().ok


def test_deleting_tail_is_detected() -> None:
    last = record(AuditEvent(action=AuditAction.LOGOUT))
    with get_engine("migrator").begin() as conn:
        saved = dict(
            conn.execute(text("SELECT * FROM core.audit_log WHERE id = :i"), {"i": last})
            .mappings().one()
        )
        conn.execute(text("DELETE FROM core.audit_log WHERE id = :i"), {"i": last})
    try:
        assert not verify_chain_snapshot().ok
    finally:
        cols = ", ".join(saved)
        vals = ", ".join(
            f"CAST(:{c} AS jsonb)" if c == "details" else f":{c}" for c in saved
        )
        saved["details"] = __import__("json").dumps(saved["details"])
        with get_engine("migrator").begin() as conn:
            conn.execute(text(f"INSERT INTO core.audit_log ({cols}) VALUES ({vals})"), saved)
    assert verify_chain_snapshot().ok


def test_app_role_cannot_update_or_delete_audit() -> None:
    record(AuditEvent(action=AuditAction.LOGOUT))
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("UPDATE core.audit_log SET result = 'ok'"))
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("DELETE FROM core.audit_log"))


def test_partitions_exist_for_next_months() -> None:
    with get_engine("app").begin() as conn:
        conn.execute(text("SELECT core.ensure_audit_partitions(3)"))
        count = conn.execute(
            text(
                "SELECT count(*) FROM pg_inherits WHERE inhparent = 'core.audit_log'::regclass "
                "AND inhrelid::regclass::text ~ 'audit_log_[0-9]{6}$'"
            )
        ).scalar_one()
    assert count >= 4
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_audit_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.audit'`.

- [ ] **Step 4: Implementatsiya**

`backend/app/audit/__init__.py`: bo'sh fayl.

`backend/app/audit/service.py`:
```python
"""O'zgarmas audit jurnali (spec 3.6).

Har yozuv alohida qisqa tranzaksiyada yoziladi — so'rov rollback bo'lsa ham (masalan,
noto'g'ri parol) hodisa yo'qolmaydi. Zanjir: hash = SHA-256(prev_hash || kanonik_json).
Zanjir boshi `core.audit_head` da FOR UPDATE qulfi ostida — parallel yozuvlar ketma-ketlashadi.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import get_engine
from app.core.logging import mask
from app.core.request_meta import ClientMeta

GENESIS = bytes(32)
CHAIN_FIELDS = (
    "id", "ts", "user_id", "action", "result", "object_type", "object_id",
    "request_id", "details", "ip_enc", "ua_enc",
)
_SELECT = (
    "SELECT id, ts, user_id, action, result, object_type, object_id, request_id, details, "
    "ip_enc, ua_enc, prev_hash, hash FROM core.audit_log"
)


class AuditAction(StrEnum):
    LOGIN_FAIL = "auth.login.fail"
    PASSWORD_OK = "auth.password.ok"
    LOGIN_OK = "auth.login.ok"
    MFA_FAIL = "auth.mfa.fail"
    MFA_ENROLLED = "auth.mfa.enrolled"
    BACKUP_CODE_USED = "auth.mfa.backup_code_used"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGED = "auth.password.changed"
    PASSWORD_CHANGE_FAIL = "auth.password.change_fail"
    SESSION_REVOKED = "auth.session.revoked"
    USER_CREATED = "admin.user.created"
    USER_UPDATED = "admin.user.updated"
    USER_BLOCKED = "admin.user.blocked"
    USER_UNBLOCKED = "admin.user.unblocked"
    USER_PASSWORD_RESET = "admin.user.password_reset"
    USER_MFA_RESET = "admin.user.mfa_reset"
    ROLE_CREATED = "admin.role.created"
    ROLE_UPDATED = "admin.role.updated"
    POSITION_CREATED = "admin.position.created"
    POSITION_UPDATED = "admin.position.updated"
    KEY_ROTATED = "admin.key.rotated"
    AUDIT_EXPORTED = "audit.exported"
    AUDIT_VERIFIED = "audit.verified"
    RLS_VIOLATION = "security.rls_violation_attempt"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    action: AuditAction
    result: str = "ok"
    user_id: int | None = None
    object_type: str | None = None
    object_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    ip: str | None = None
    ua: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ChainReport:
    ok: bool
    checked: int
    first_bad_id: int | None


def ip_aad(audit_id: int) -> str:
    return f"core.audit_log.ip:{audit_id}"


def ua_aad(audit_id: int) -> str:
    return f"core.audit_log.ua:{audit_id}"


def _encode(value: Any) -> Any:
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value).hex()
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value


def canonical(row: dict[str, Any] | RowMapping) -> bytes:
    payload = {name: _encode(row[name]) for name in CHAIN_FIELDS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def chain_hash(prev: bytes, row: dict[str, Any] | RowMapping) -> bytes:
    return hashlib.sha256(prev + canonical(row)).digest()


def record(event: AuditEvent) -> int:
    details = mask(event.details)
    with get_engine("app").begin() as conn:
        prev = bytes(
            conn.execute(
                text("SELECT last_hash FROM core.audit_head WHERE id = 1 FOR UPDATE")
            ).scalar_one()
        )
        audit_id = int(conn.execute(text("SELECT nextval('core.audit_log_id_seq')")).scalar_one())
        row: dict[str, Any] = {
            "id": audit_id,
            "ts": datetime.now(UTC),
            "user_id": event.user_id,
            "action": str(event.action),
            "result": event.result,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "request_id": event.request_id,
            "details": details,
            "ip_enc": (
                keystore.encrypt_str(Purpose.AUDIT, event.ip, ip_aad(audit_id)) if event.ip else None
            ),
            "ua_enc": (
                keystore.encrypt_str(Purpose.AUDIT, event.ua[:512], ua_aad(audit_id))
                if event.ua
                else None
            ),
        }
        digest = chain_hash(prev, row)
        conn.execute(
            text(
                "INSERT INTO core.audit_log (id, ts, user_id, action, result, object_type, "
                "object_id, request_id, details, ip_enc, ua_enc, prev_hash, hash) VALUES "
                "(:id, :ts, :user_id, :action, :result, :object_type, :object_id, :request_id, "
                "CAST(:details AS jsonb), :ip_enc, :ua_enc, :prev_hash, :hash)"
            ),
            {**row, "details": json.dumps(details, ensure_ascii=False), "prev_hash": prev,
             "hash": digest},
        )
        conn.execute(
            text("UPDATE core.audit_head SET last_id = :id, last_hash = :h WHERE id = 1"),
            {"id": audit_id, "h": digest},
        )
    return audit_id


def log_event(
    meta: ClientMeta,
    action: AuditAction,
    *,
    user_id: int | None,
    result: str = "ok",
    object_type: str | None = None,
    object_id: object | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    return record(
        AuditEvent(
            action=action,
            result=result,
            user_id=user_id,
            object_type=object_type,
            object_id=None if object_id is None else str(object_id),
            details=details or {},
            ip=meta.ip,
            ua=meta.ua,
            request_id=meta.request_id,
        )
    )


def verify_chain(conn: Connection) -> ChainReport:
    """REPEATABLE READ tranzaksiyasi ichida chaqirilishi kerak (verify_chain_snapshot)."""
    head_id, head_hash = conn.execute(
        text("SELECT last_id, last_hash FROM core.audit_head WHERE id = 1")
    ).one()
    prev: bytes | None = None
    last_id: int | None = None
    checked = 0
    result = conn.execution_options(stream_results=True, yield_per=1000).execute(
        text(f"{_SELECT} ORDER BY id")
    )
    for row in result.mappings():
        stored_prev = bytes(row["prev_hash"])
        if prev is not None and stored_prev != prev:
            return ChainReport(False, checked, row["id"])
        expected = chain_hash(stored_prev, row)
        if expected != bytes(row["hash"]):
            return ChainReport(False, checked, row["id"])
        prev, last_id, checked = expected, row["id"], checked + 1
    if head_id != last_id or (prev is not None and bytes(head_hash) != prev):
        return ChainReport(False, checked, head_id)
    return ChainReport(True, checked, None)


def verify_chain_snapshot() -> ChainReport:
    engine = get_engine("app")
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            return verify_chain(conn)
```

`backend/app/bootstrap.py` — `ensure_keys` qatoridan keyin qo'shing:
```python
        conn.execute(text("SELECT core.ensure_audit_partitions(3)"))
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(audit): hash-chain audit jurnali, shifrlangan IP/UA, oylik partitsiyalar"
```

---

### Task 7: Parollar (Argon2id, siyosat) va TOTP/zaxira kodlar

**Files:**
- Create: `backend/app/auth/passwords.py`, `backend/app/auth/totp.py`, `backend/app/auth/data/__init__.py`, `backend/app/auth/data/common-passwords.txt.gz`
- Test: `backend/tests/test_passwords.py`, `backend/tests/test_totp.py`

**Interfaces:**
- Produces:
  - `app.auth.passwords`: `STANDARD_PARAMS = (3, 65536, 4)`, `FAST_TEST_PARAMS`, `MIN_LENGTH = 12`, `HISTORY_DEPTH = 5`, `hash_password(pw) -> str`, `verify_password(pw, hash) -> bool`, `needs_rehash(hash) -> bool`, `dummy_verify(pw) -> None`, `policy_problems(pw, *, username, previous_hashes=()) -> list[str]` (kodlar: `password_too_short`, `password_too_simple`, `password_contains_username`, `password_common`, `password_reused`), `generate_temporary_password(length=16) -> str`.
  - `app.auth.totp`: `ISSUER = "UGEKAZNA"`, `STEP_SECONDS = 30`, `BACKUP_CODE_COUNT = 10`, `new_secret() -> str`, `provisioning_uri(secret, username) -> str`, `qr_data_uri(uri) -> str`, `verify(secret, code, last_step: int | None, now: float) -> int | None`, `generate_backup_codes() -> list[str]` (`XXXXX-XXXXX`), `normalize_backup_code(code) -> str | None`.

- [ ] **Step 1: Keng tarqalgan parollar ro'yxati**

```bash
mkdir -p backend/app/auth/data && touch backend/app/auth/data/__init__.py
curl -fsSL --cacert backend/certs/organization-ca-3.crt \
  "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Common-Credentials/10-million-password-list-top-100000.txt" \
  -o /tmp/common.txt || curl -fsSL \
  "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Common-Credentials/10-million-password-list-top-100000.txt" \
  -o /tmp/common.txt
wc -l /tmp/common.txt
gzip -9 -c /tmp/common.txt > backend/app/auth/data/common-passwords.txt.gz
```
Expected: `100000` atrofida qator. URL o'zgargan bo'lsa — SecLists repo'sining `Passwords/Common-Credentials/` papkasidan top-100000 faylini oling.

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_passwords.py`:
```python
from app.auth import passwords
from app.auth.passwords import (
    STANDARD_PARAMS,
    generate_temporary_password,
    hash_password,
    needs_rehash,
    policy_problems,
    verify_password,
)

GOOD = "Kuchli-Parol-2026!"


def test_standard_params_match_spec() -> None:
    assert STANDARD_PARAMS == (3, 65536, 4)


def test_hash_and_verify() -> None:
    h = hash_password(GOOD)
    assert h.startswith("$argon2id$")
    assert verify_password(GOOD, h)
    assert not verify_password("boshqa", h)
    assert not verify_password(GOOD, "not-a-hash")
    assert not needs_rehash(h)


def test_dummy_verify_does_not_raise() -> None:
    passwords.dummy_verify("anything")


def test_good_password_passes() -> None:
    assert policy_problems(GOOD, username="ali.valiyev") == []


def test_short_and_simple() -> None:
    assert "password_too_short" in policy_problems("Ab1!", username="u")
    assert "password_too_simple" in policy_problems("abcdefghijklmn", username="u")


def test_contains_username_case_insensitive() -> None:
    assert "password_contains_username" in policy_problems("XX-ALI.VALIYEV-2026", username="ali.valiyev")


def test_common_and_context_words() -> None:
    assert "password_common" in policy_problems("Ugekazna-2026!", username="u")
    assert "password_common" in policy_problems("Qwerty-12345!", username="u")


def test_reused_password() -> None:
    old = hash_password(GOOD)
    assert policy_problems(GOOD, username="u", previous_hashes=[old]) == ["password_reused"]


def test_temporary_passwords_satisfy_policy() -> None:
    samples = {generate_temporary_password() for _ in range(50)}
    assert len(samples) == 50
    assert all(len(p) == 16 and policy_problems(p, username="user") == [] for p in samples)
```

`backend/tests/test_totp.py`:
```python
import time

import pyotp

from app.auth import totp


def test_verify_accepts_current_and_blocks_replay() -> None:
    secret = totp.new_secret()
    now = time.time()
    code = pyotp.TOTP(secret).at(now)
    step = totp.verify(secret, code, None, now)
    assert step == int(now) // 30
    assert totp.verify(secret, code, step, now) is None


def test_verify_window_is_plus_minus_one_step() -> None:
    secret = totp.new_secret()
    now = time.time()
    current = int(now) // 30
    prev_code = pyotp.TOTP(secret).at((current - 1) * 30)
    far_code = pyotp.TOTP(secret).at((current + 2) * 30)
    assert totp.verify(secret, prev_code, None, now) == current - 1
    assert totp.verify(secret, far_code, None, now) is None


def test_verify_rejects_malformed() -> None:
    secret = totp.new_secret()
    for bad in ("", "12345", "1234567", "abcdef", "12 345"):
        assert totp.verify(secret, bad, None, time.time()) is None


def test_secret_is_160_bits() -> None:
    assert len(totp.new_secret()) == 32


def test_provisioning_uri_and_qr() -> None:
    uri = totp.provisioning_uri(totp.new_secret(), "ali.valiyev")
    assert uri.startswith("otpauth://totp/UGEKAZNA:ali.valiyev?")
    assert "issuer=UGEKAZNA" in uri
    assert totp.qr_data_uri(uri).startswith("data:image/svg+xml")


def test_backup_codes() -> None:
    codes = totp.generate_backup_codes()
    assert len(codes) == totp.BACKUP_CODE_COUNT == len(set(codes))
    for c in codes:
        assert len(c) == 11 and c[5] == "-"
        assert totp.normalize_backup_code(c) == c.replace("-", "")
        assert totp.normalize_backup_code(c.lower().replace("-", " ")) == c.replace("-", "")
    assert totp.normalize_backup_code("123456") is None
    assert totp.normalize_backup_code("ABCDE-FGH") is None
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_passwords.py tests/test_totp.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 4: Implementatsiya**

`backend/app/auth/passwords.py`:
```python
"""Parollar: Argon2id va parol siyosati (spec 3.1)."""

from __future__ import annotations

import gzip
import secrets
import string
from collections.abc import Sequence
from functools import lru_cache
from importlib import resources

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

STANDARD_PARAMS = (3, 64 * 1024, 4)  # time_cost, memory_cost (KiB), parallelism
FAST_TEST_PARAMS = (1, 8 * 1024, 1)
MIN_LENGTH = 12
HISTORY_DEPTH = 5
CONTEXT_WORDS = ("ugekazna", "gidroenergo", "password", "parol", "qwerty", "admin")
_TEMP_ALPHABET = string.ascii_letters + string.digits + "-_!@#%+="


def _make_hasher() -> PasswordHasher:
    fast = get_settings().argon2_profile == "fast_test"
    t, m, p = FAST_TEST_PARAMS if fast else STANDARD_PARAMS
    return PasswordHasher(time_cost=t, memory_cost=m, parallelism=p, hash_len=32, salt_len=16)


_hasher = _make_hasher()
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def dummy_verify(password: str) -> None:
    """Foydalanuvchi topilmaganda ham bir xil vaqt sarflaydi (timing attack'dan himoya)."""
    verify_password(password, _DUMMY_HASH)


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    raw = resources.files("app.auth.data").joinpath("common-passwords.txt.gz").read_bytes()
    lines = gzip.decompress(raw).decode("utf-8", "ignore").splitlines()
    return frozenset(line.strip().casefold() for line in lines if line.strip())


def _classes(password: str) -> int:
    return sum(
        (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        )
    )


def policy_problems(
    password: str, *, username: str, previous_hashes: Sequence[str] = ()
) -> list[str]:
    problems: list[str] = []
    if len(password) < MIN_LENGTH:
        problems.append("password_too_short")
    if _classes(password) < 3:
        problems.append("password_too_simple")
    folded = password.casefold()
    if username and username.casefold() in folded:
        problems.append("password_contains_username")
    if folded in _common_passwords() or any(w in folded for w in CONTEXT_WORDS):
        problems.append("password_common")
    if not problems and any(verify_password(password, h) for h in previous_hashes):
        problems.append("password_reused")
    return problems


def generate_temporary_password(length: int = 16) -> str:
    while True:
        candidate = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))
        if not policy_problems(candidate, username=""):
            return candidate
```

`backend/app/auth/totp.py`:
```python
"""TOTP (RFC 6238) va bir martalik zaxira kodlar."""

from __future__ import annotations

import hmac
import re
import secrets

import pyotp
import segno

ISSUER = "UGEKAZNA"
STEP_SECONDS = 30
DIGITS = 6
BACKUP_CODE_COUNT = 10
_BACKUP_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # I, L, O, 0, 1 yo'q
_BACKUP_RE = re.compile(r"^[A-Z0-9]{5}-?[A-Z0-9]{5}$")


def new_secret() -> str:
    return str(pyotp.random_base32(length=32))


def _totp(secret: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret, digits=DIGITS, interval=STEP_SECONDS)


def provisioning_uri(secret: str, username: str) -> str:
    return str(_totp(secret).provisioning_uri(name=username, issuer_name=ISSUER))


def qr_data_uri(uri: str) -> str:
    return str(segno.make(uri, error="m").svg_data_uri(scale=5, border=2))


def verify(secret: str, code: str, last_step: int | None, now: float) -> int | None:
    """Mos kelgan qadam raqamini qaytaradi. `last_step` va undan oldingilari qabul qilinmaydi."""
    code = code.strip()
    if len(code) != DIGITS or not code.isdigit():
        return None
    otp = _totp(secret)
    current = int(now) // STEP_SECONDS
    for step in (current - 1, current, current + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(str(otp.at(step * STEP_SECONDS)), code):
            return step
    return None


def generate_backup_codes() -> list[str]:
    codes: set[str] = set()
    while len(codes) < BACKUP_CODE_COUNT:
        raw = "".join(secrets.choice(_BACKUP_ALPHABET) for _ in range(10))
        codes.add(f"{raw[:5]}-{raw[5:]}")
    return sorted(codes)


def normalize_backup_code(code: str) -> str | None:
    cleaned = code.strip().upper().replace(" ", "")
    if not _BACKUP_RE.match(cleaned):
        return None
    return cleaned.replace("-", "")
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(auth): Argon2id parol siyosati, TOTP va zaxira kodlar"
```

---

### Task 8: Rate limit (Redis) va readyz'da Redis tekshiruvi

**Files:**
- Create: `backend/app/core/ratelimit.py`
- Modify: `backend/app/health/router.py`
- Test: `backend/tests/test_ratelimit.py`

**Interfaces:**
- Consumes: `Settings.redis_url`, `RateLimitedError`, `get_logger`.
- Produces: `app.core.ratelimit`: `Limit(events, window)`, `LOGIN_PER_IP = Limit(10, 60)`, `MFA_PER_IP = Limit(20, 60)`, `API_PER_USER = Limit(300, 60)`, `check(scope, identity, limit) -> int` (qolgan urinishlar), `reset(scope, identity)`, `ping() -> bool`, `_client_override` (testlar uchun).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_ratelimit.py`:
```python
import uuid

import pytest
import redis

from app.core import ratelimit
from app.core.errors import RateLimitedError
from app.core.ratelimit import Limit


def test_limit_exceeded_raises_with_retry_after() -> None:
    ident = uuid.uuid4().hex
    limit = Limit(events=3, window=60)
    assert [ratelimit.check("t", ident, limit) for _ in range(3)] == [2, 1, 0]
    with pytest.raises(RateLimitedError) as exc:
        ratelimit.check("t", ident, limit)
    assert 1 <= exc.value.params["retry_after"] <= 60
    assert exc.value.headers["Retry-After"] == str(exc.value.params["retry_after"])


def test_identities_are_independent_and_reset_works() -> None:
    a, b = uuid.uuid4().hex, uuid.uuid4().hex
    limit = Limit(events=1, window=60)
    ratelimit.check("t", a, limit)
    ratelimit.check("t", b, limit)
    ratelimit.reset("t", a)
    assert ratelimit.check("t", a, limit) == 0


def test_redis_down_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ratelimit, "_last_failure", 0.0)  # test oxirida qayta tiklanadi
    dead = redis.Redis(host="127.0.0.1", port=1, socket_timeout=0.2, socket_connect_timeout=0.2)
    monkeypatch.setattr(ratelimit, "_client_override", dead)
    limit = Limit(events=1, window=60)
    assert ratelimit.check("t", "x", limit) == 1
    assert ratelimit.check("t", "x", limit) == 1
    assert ratelimit.ping() is False


def test_ping_ok() -> None:
    assert ratelimit.ping() is True
```

`backend/tests/conftest.py` — quyidagini qo'shing (import'lar fayl boshiga; har test oldidan limit hisoblagichlari tozalanadi):
```python
import redis as redis_lib

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_rate_limits() -> None:
    client = redis_lib.Redis.from_url(get_settings().redis_url)
    for key in client.scan_iter("rl:*"):
        client.delete(key)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_ratelimit.py -v`
Expected: FAIL — `ImportError: cannot import name 'ratelimit'`.

- [ ] **Step 3: Implementatsiya**

`backend/app/core/ratelimit.py`:
```python
"""So'rov chastotasini cheklash (Redis, qat'iy oyna).

Redis ishlamasa cheklov vaqtincha O'CHADI (fail-open) va WARNING yoziladi: kesh
tushgani uchun butun tizim to'xtamasligi kerak. Login uchun DB'dagi blok (5 xato →
15 daqiqa) Redis'ga bog'liq emas va baribir ishlaydi.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import redis

from app.core.config import get_settings
from app.core.errors import RateLimitedError
from app.core.logging import get_logger

log = get_logger("ugekazna.ratelimit")
RETRY_CLIENT_AFTER = 30.0


@dataclass(frozen=True, slots=True)
class Limit:
    events: int
    window: int


LOGIN_PER_IP = Limit(events=10, window=60)
MFA_PER_IP = Limit(events=20, window=60)
API_PER_USER = Limit(events=300, window=60)

_client_override: redis.Redis | None = None
_lock = threading.Lock()
_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client_override is not None:
        return _client_override
    with _lock:
        if _client is None:
            _client = redis.Redis.from_url(
                get_settings().redis_url, socket_timeout=1, socket_connect_timeout=1
            )
        return _client


_last_failure = 0.0


def check(scope: str, identity: str, limit: Limit) -> int:
    """Hisoblagichni oshiradi, qolgan urinishlar sonini qaytaradi; oshsa RateLimitedError."""
    global _last_failure
    key = f"rl:{scope}:{identity}"
    if _client_override is None and time.monotonic() - _last_failure < RETRY_CLIENT_AFTER:
        return limit.events
    try:
        pipe = _get_client().pipeline()
        pipe.incr(key)
        pipe.expire(key, limit.window, nx=True)
        pipe.ttl(key)
        count, _, ttl = pipe.execute()
    except redis.RedisError as exc:
        _last_failure = time.monotonic()
        log.warning("ratelimit_unavailable", error=type(exc).__name__)
        return limit.events
    if int(count) > limit.events:
        raise RateLimitedError(retry_after=max(1, int(ttl)))
    return limit.events - int(count)


def reset(scope: str, identity: str) -> None:
    try:
        _get_client().delete(f"rl:{scope}:{identity}")
    except redis.RedisError:
        log.warning("ratelimit_reset_failed")


def ping() -> bool:
    try:
        return bool(_get_client().ping())
    except redis.RedisError:
        return False
```

Eslatma: `test_redis_down_fails_open` `_client_override` ni o'rnatadi, shuning uchun `_last_failure` oynasi override'da hisobga olinmaydi (har chaqiruv haqiqatan Redis'ga urinadi va fail-open qaytaradi).

`backend/app/health/router.py` — `readyz` ichida `checks` ni almashtiring va import qo'shing:
```python
from app.core import ratelimit
```
```python
    checks = {"db": _db_ok(), "redis": ratelimit.ping()}
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(core): Redis rate limit (fail-open), readyz'da Redis tekshiruvi"
```

---

### Task 9: Sessiyalar, AuthContext, `get_ctx` va `require_perm`

**Files:**
- Create: `backend/app/auth/sessions.py`, `backend/app/auth/context.py`, `backend/tests/helpers.py`
- Modify: `backend/tests/conftest.py` (`make_user` fixture)
- Test: `backend/tests/test_context.py`

**Interfaces:**
- Consumes: `UserSession`, `User`, `Role`, `Position`, `PositionBranch`, `RolePermission`, `keystore.encrypt_str`, `keystore.pepper`, `keyed_hash`, `apply_rls`, `ratelimit.check/API_PER_USER`, `AuthError`, `ForbiddenError`, `PasswordChangeRequired`, `ScopeViolationError`.
- Produces:
  - `app.auth.sessions`: `NewSession(id: uuid.UUID, token: str, csrf: str, absolute_expires_at: datetime)`, `token_hmac(token) -> bytes`, `ip_aad(session_id) -> str`, `create(db, user_id, ip, ua, now) -> NewSession`, `resolve(db, token, now) -> tuple[UserSession, User] | None`, `revoke(db, session_id, reason, now)`, `revoke_all(db, user_id, reason, now, except_id=None) -> int`, `ua_summary(ua) -> str`.
  - `app.auth.context`: `AuthContext(user_id, username, full_name, role_code, permissions, branch_ids, session_id, must_change_password)` + `.has(p)`, `.require(*p)`, `.assert_branch(branch_id)`; `SESSION_COOKIE = "__Host-ugk_session"`, `CSRF_COOKIE = "__Host-ugk_csrf"`, `CSRF_HEADER = "X-CSRF-Token"`, `UNSAFE_METHODS`, `PASSWORD_CHANGE_ALLOWED`, `load_scope(db, user)`, `build_context(db, user, session_id, now) -> AuthContext`, `get_ctx(...) -> AuthContext`, `require_perm(*perms)` (qaytgan funksiyada `.required_perms: frozenset[str]`), `Ctx`.
  - `tests.helpers`: `SeedUser(id, username, password, totp_secret)` + `.next_code()`, `create_user(role="admin", *, branch_ids=(), totp=True, must_change=False, password=DEFAULT_PASSWORD) -> SeedUser`, `issue_session(user_id) -> tuple[str, str, uuid.UUID]`, `use_session(client, token, csrf)`, `login(client, user) -> TestClient`, `DEFAULT_PASSWORD`.

- [ ] **Step 1: Test yordamchilari**

`backend/tests/helpers.py`:
```python
"""Testlar uchun foydalanuvchi va sessiya yaratish yordamchilari."""

from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import sessions
from app.auth.context import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.auth.models import Position, PositionBranch, Role, User
from app.auth.passwords import hash_password
from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import new_session

DEFAULT_PASSWORD = "Sinov-Kalit-2026!"
_counter = itertools.count()


@dataclass
class SeedUser:
    id: int
    username: str
    password: str
    totp_secret: str | None
    _step: int = field(default=0)

    def next_code(self) -> str:
        """Har chaqiruvda keyingi TOTP qadami — replay himoyasi testlarni yiqitmasligi uchun."""
        assert self.totp_secret is not None
        now_step = int(time.time()) // 30
        self._step = max(self._step + 1, now_step - 1)
        if self._step > now_step + 1:
            time.sleep(30 - time.time() % 30 + 0.1)
            return self.next_code()
        return str(pyotp.TOTP(self.totp_secret).at(self._step * 30))


def create_user(
    role: str = "admin",
    *,
    branch_ids: tuple[int, ...] = (),
    totp: bool = True,
    must_change: bool = False,
    password: str = DEFAULT_PASSWORD,
) -> SeedUser:
    username = f"u{next(_counter)}_{uuid.uuid4().hex[:8]}"
    with new_session() as s:
        role_id = s.execute(select(Role.id).where(Role.code == role)).scalar_one()
        position = Position(code=f"p_{username}", name=f"Test {role}", role_id=role_id)
        s.add(position)
        s.flush()
        for branch in branch_ids:
            s.add(PositionBranch(position_id=position.id, branch_id=branch))
        user = User(
            username=username,
            full_name="Тестовый Пользователь",
            position_id=position.id,
            password_hash=hash_password(password),
            password_changed_at=datetime.now(UTC),
            must_change_password=must_change,
            totp_enabled=totp,
        )
        s.add(user)
        s.flush()
        secret = pyotp.random_base32(32) if totp else None
        if secret:
            user.totp_secret_enc = keystore.encrypt_str(
                Purpose.MFA, secret, f"core.users.totp_secret_enc:{user.id}"
            )
        s.commit()
        return SeedUser(id=user.id, username=username, password=password, totp_secret=secret)


def issue_session(user_id: int) -> tuple[str, str, uuid.UUID]:
    with new_session() as s:
        new = sessions.create(s, user_id, "10.0.0.1", "pytest", datetime.now(UTC))
        s.commit()
    return new.token, new.csrf, new.id


def use_session(client: TestClient, token: str, csrf: str) -> TestClient:
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf)
    client.headers[CSRF_HEADER] = csrf
    return client


def login(client: TestClient, user: SeedUser) -> TestClient:
    r = client.post("/api/v1/auth/login", json={"username": user.username, "password": user.password})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next"] == "mfa_verify", body
    r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": body["mfa_token"], "code": user.next_code()})
    assert r.status_code == 200, r.text
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    return client
```

`backend/tests/conftest.py` — quyidagini qo'shing (import'lar fayl boshiga):
```python
from collections.abc import Callable

from tests.helpers import SeedUser, create_user


@pytest.fixture
def make_user() -> Callable[..., SeedUser]:
    return create_user
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_context.py`:
```python
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.auth import context as context_module
from app.auth import sessions
from app.auth.context import SESSION_COOKIE, Ctx, require_perm
from app.auth.models import User, UserSession
from app.auth.permissions import Perm
from app.core.db import get_db, new_session
from app.main import create_app
from tests.helpers import SeedUser, issue_session, use_session


def _app() -> FastAPI:
    app = create_app()

    @app.get("/api/v1/_probe")
    def probe(ctx: Ctx, db: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
        return {
            "user": ctx.username,
            "branches": db.execute(text("SELECT current_setting('app.branch_ids', true)")).scalar_one(),
            "all": db.execute(text("SELECT current_setting('app.scope_all', true)")).scalar_one(),
        }

    @app.post("/api/v1/_probe")
    def probe_post(ctx: Ctx) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/_admin", dependencies=[Depends(require_perm(Perm.ADMIN_USERS))])
    def admin_only() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
def client() -> TestClient:
    with TestClient(_app(), base_url="https://testserver") as c:
        yield c


def _set(session_id: object, **values: object) -> None:
    with new_session() as s:
        s.execute(update(UserSession).where(UserSession.id == session_id).values(**values))
        s.commit()


def test_no_cookie_is_401(client: TestClient) -> None:
    r = client.get("/api/v1/_probe")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


def test_valid_session_and_rls_for_global_user(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user("admin")
    use_session(client, *issue_session(user.id)[:2])
    r = client.get("/api/v1/_probe")
    assert r.status_code == 200
    assert r.json() == {"user": user.username, "branches": "{}", "all": "on"}


def test_branch_user_gets_own_branches(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user("economist_filiala", branch_ids=(3, 7))
    use_session(client, *issue_session(user.id)[:2])
    assert client.get("/api/v1/_probe").json()["branches"] == "{3,7}"
    assert client.get("/api/v1/_probe").json()["all"] == "off"


def test_garbage_token_is_401(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "garbage")
    assert client.get("/api/v1/_probe").json()["error"]["code"] == "session_expired"


@pytest.mark.parametrize("field", ["idle_expires_at", "absolute_expires_at", "revoked_at"])
def test_expired_or_revoked_session_is_401(
    client: TestClient, make_user: Callable[..., SeedUser], field: str
) -> None:
    user = make_user()
    token, csrf, sid = issue_session(user.id)
    _set(sid, **{field: datetime.now(UTC) - timedelta(seconds=1)})
    use_session(client, token, csrf)
    assert client.get("/api/v1/_probe").status_code == 401


def test_blocked_user_session_rejected(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    use_session(client, *issue_session(user.id)[:2])
    assert client.get("/api/v1/_probe").status_code == 200
    with new_session() as s:
        s.execute(update(User).where(User.id == user.id).values(is_active=False))
        s.commit()
    assert client.get("/api/v1/_probe").status_code == 401


def test_csrf_required_for_unsafe_methods(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    token, csrf, _ = issue_session(user.id)
    use_session(client, token, csrf)
    assert client.post("/api/v1/_probe").status_code == 200
    client.headers["X-CSRF-Token"] = "wrong"
    r = client.post("/api/v1/_probe")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_permission_required(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    use_session(client, *issue_session(make_user("rukovodstvo").id)[:2])
    assert client.get("/api/v1/_admin").status_code == 403
    use_session(client, *issue_session(make_user("admin").id)[:2])
    assert client.get("/api/v1/_admin").status_code == 200


def test_must_change_password_blocks_other_routes(
    client: TestClient, make_user: Callable[..., SeedUser], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = make_user(must_change=True)
    use_session(client, *issue_session(user.id)[:2])
    r = client.get("/api/v1/_probe")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "password_change_required"
    monkeypatch.setattr(context_module, "PASSWORD_CHANGE_ALLOWED", frozenset({"/api/v1/_probe"}))
    assert client.get("/api/v1/_probe").status_code == 200


def test_expired_password_counts_as_must_change(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    with new_session() as s:
        s.execute(
            update(User).where(User.id == user.id)
            .values(password_changed_at=datetime.now(UTC) - timedelta(days=91))
        )
        s.commit()
    use_session(client, *issue_session(user.id)[:2])
    assert client.get("/api/v1/_probe").json()["error"]["code"] == "password_change_required"


def test_session_slides_idle_expiry(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    token, csrf, sid = issue_session(user.id)
    old = datetime.now(UTC) - timedelta(minutes=5)
    _set(sid, last_seen_at=old, idle_expires_at=old + timedelta(minutes=30))
    use_session(client, token, csrf)
    assert client.get("/api/v1/_probe").status_code == 200
    with new_session() as s:
        row = s.get(UserSession, sid)
        assert row is not None
        assert row.last_seen_at > old + timedelta(minutes=4)
        assert row.idle_expires_at > datetime.now(UTC) + timedelta(minutes=29)


def test_ua_summary() -> None:
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
    assert sessions.ua_summary(ua) == "Chrome · Windows"
    assert sessions.ua_summary(None) == "—"


def test_session_ip_is_encrypted(make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    _, _, sid = issue_session(user.id)
    with new_session() as s:
        row = s.get(UserSession, sid)
        assert row is not None and row.ip_enc is not None
        assert b"10.0.0.1" not in row.ip_enc
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_context.py -v`
Expected: FAIL — `ImportError: cannot import name 'sessions' from 'app.auth'`.

- [ ] **Step 4: Implementatsiya**

`backend/app/auth/sessions.py`:
```python
"""Server tomonidagi sessiyalar (spec 3.2). DB'da token emas, uning HMAC'i saqlanadi."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from app.auth.models import User, UserSession
from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose, keyed_hash

SLIDE_EVERY = timedelta(seconds=60)
_BROWSERS = (
    ("Edg/", "Edge"), ("OPR/", "Opera"), ("YaBrowser", "Яндекс"),
    ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari"),
)
_OSES = (
    ("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iOS"),
    ("iPad", "iPadOS"), ("Mac OS X", "macOS"), ("Linux", "Linux"),
)


@dataclass(frozen=True, slots=True)
class NewSession:
    id: uuid.UUID
    token: str
    csrf: str
    absolute_expires_at: datetime


def token_hmac(token: str) -> bytes:
    return keyed_hash(keystore.pepper(), "session", token)


def ip_aad(session_id: uuid.UUID) -> str:
    return f"core.sessions.ip_enc:{session_id}"


def ua_summary(ua: str | None) -> str:
    if not ua:
        return "—"
    browser = next((name for token, name in _BROWSERS if token in ua), "Браузер")
    system = next((name for token, name in _OSES if token in ua), "")
    return f"{browser} · {system}" if system else browser


def create(db: Session, user_id: int, ip: str | None, ua: str | None, now: datetime) -> NewSession:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    session_id = uuid.uuid4()
    absolute = now + timedelta(hours=settings.session_absolute_hours)
    db.add(
        UserSession(
            id=session_id,
            user_id=user_id,
            token_hmac=token_hmac(token),
            created_at=now,
            last_seen_at=now,
            idle_expires_at=min(now + timedelta(minutes=settings.session_idle_minutes), absolute),
            absolute_expires_at=absolute,
            ip_enc=keystore.encrypt_str(Purpose.PII, ip, ip_aad(session_id)) if ip else None,
            ua_summary=ua_summary(ua)[:80],
        )
    )
    db.flush()
    return NewSession(session_id, token, secrets.token_urlsafe(32), absolute)


def resolve(db: Session, token: str, now: datetime) -> tuple[UserSession, User] | None:
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hmac == token_hmac(token))
    ).first()
    if row is None:
        return None
    sess, user = row
    if (
        sess.revoked_at is not None
        or sess.idle_expires_at <= now
        or sess.absolute_expires_at <= now
        or not user.is_active
    ):
        return None
    if now - sess.last_seen_at >= SLIDE_EVERY:
        idle = timedelta(minutes=get_settings().session_idle_minutes)
        sess.last_seen_at = now
        sess.idle_expires_at = min(now + idle, sess.absolute_expires_at)
    return sess, user


def revoke(db: Session, session_id: uuid.UUID, reason: str, now: datetime) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoke_reason=reason)
    )


def revoke_all(
    db: Session, user_id: int, reason: str, now: datetime, except_id: uuid.UUID | None = None
) -> int:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoke_reason=reason)
    )
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    return cast(CursorResult[Any], db.execute(stmt)).rowcount
```

`backend/app/auth/context.py`:
```python
"""Har so'rov uchun "kim va nimaga haqli" (spec 3.3–3.4). Tekshiruv faqat serverda."""

from __future__ import annotations

import hmac
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import sessions
from app.auth.models import Position, PositionBranch, Role, RolePermission, User
from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import apply_rls, get_db
from app.core.errors import AuthError, ForbiddenError, PasswordChangeRequired, ScopeViolationError

SESSION_COOKIE = "__Host-ugk_session"
CSRF_COOKIE = "__Host-ugk_csrf"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
PASSWORD_CHANGE_ALLOWED = frozenset(
    {"/api/v1/auth/me", "/api/v1/auth/password/change", "/api/v1/auth/logout"}
)


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: int
    username: str
    full_name: str
    role_code: str
    permissions: frozenset[str]
    branch_ids: frozenset[int] | None  # None — barcha filiallar
    session_id: uuid.UUID
    must_change_password: bool = False

    def has(self, perm: str) -> bool:
        return perm in self.permissions

    def require(self, *perms: str) -> None:
        if not all(p in self.permissions for p in perms):
            raise ForbiddenError()

    def assert_branch(self, branch_id: int | None) -> None:
        """So'ralgan filial foydalanuvchi doirasida ekanini tekshiradi (`None` — "hammasi")."""
        if branch_id is None or self.branch_ids is None:
            return
        if branch_id not in self.branch_ids:
            raise ScopeViolationError(branch_id=branch_id)


def load_scope(db: Session, user: User) -> tuple[str, frozenset[str], frozenset[int] | None]:
    row = db.execute(
        select(Role.id, Role.code, Role.scope_all)
        .join(Position, Position.role_id == Role.id)
        .where(Position.id == user.position_id, Position.is_active.is_(True))
    ).one_or_none()
    if row is None:
        return "", frozenset(), frozenset()
    role_id, role_code, scope_all = row
    perms = frozenset(
        db.execute(
            select(RolePermission.permission_code).where(RolePermission.role_id == role_id)
        ).scalars()
    )
    if scope_all:
        return role_code, perms, None
    branches = frozenset(
        db.execute(
            select(PositionBranch.branch_id).where(PositionBranch.position_id == user.position_id)
        ).scalars()
    )
    return role_code, perms, branches


def build_context(db: Session, user: User, session_id: uuid.UUID, now: datetime) -> AuthContext:
    role_code, perms, branches = load_scope(db, user)
    max_age = timedelta(days=get_settings().password_max_age_days)
    return AuthContext(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role_code=role_code,
        permissions=perms,
        branch_ids=branches,
        session_id=session_id,
        must_change_password=user.must_change_password or user.password_changed_at + max_age <= now,
    )


def get_ctx(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> AuthContext:
    if not session_cookie:
        raise AuthError("unauthenticated")
    now = datetime.now(UTC)
    resolved = sessions.resolve(db, session_cookie, now)
    if resolved is None:
        raise AuthError("session_expired")
    sess, user = resolved
    if request.method in UNSAFE_METHODS and not (
        csrf_cookie and csrf_header and hmac.compare_digest(csrf_cookie, csrf_header)
    ):
        raise ForbiddenError("csrf_failed")
    ratelimit.check("api_user", str(user.id), ratelimit.API_PER_USER)
    ctx = build_context(db, user, sess.id, now)
    if ctx.must_change_password and request.url.path not in PASSWORD_CHANGE_ALLOWED:
        raise PasswordChangeRequired()
    apply_rls(db, ctx.branch_ids)
    request.state.auth = ctx
    request.state.user_id = user.id
    return ctx


Ctx = Annotated[AuthContext, Depends(get_ctx)]


def require_perm(*perms: str) -> Callable[..., AuthContext]:
    """Endpoint ruxsati. Deny-by-default: tests/test_route_guards.py har route'ni tekshiradi."""

    def dependency(ctx: Ctx) -> AuthContext:
        ctx.require(*perms)
        return ctx

    dependency.required_perms = frozenset(perms)  # type: ignore[attr-defined]
    return dependency
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(auth): server sessiyalari, CSRF, AuthContext va RLS kontekstini o'rnatish"
```

---

### Task 10: Auth API — login, 2FA (verify/enroll), parol almashtirish, sessiyalar

**Files:**
- Create: `backend/app/auth/service.py`, `backend/app/auth/schemas.py`, `backend/app/auth/router.py`
- Modify: `backend/app/main.py` (router)
- Test: `backend/tests/test_auth_api.py`

**Interfaces:**
- Consumes: `passwords.*`, `totp.*`, `sessions.*`, `build_context`, `Ctx`, `audit.log_event`, `AuditAction`, `ratelimit`, `Meta`, `keystore`, `keyed_hash`.
- Produces:
  - `app.auth.service`: `normalize_username(raw) -> str`, `totp_aad(user_id) -> str` (`"core.users.totp_secret_enc:{id}"`), `LoginResult(next, mfa_token)`, `EnrollStart(otpauth_uri, qr_svg_data_uri, secret)`, `login(db, username, password, meta, now) -> LoginResult`, `verify_mfa(db, token, code, meta, now) -> tuple[NewSession, User]`, `enroll_start(db, token, now) -> EnrollStart`, `enroll_confirm(db, token, code, meta, now) -> tuple[NewSession, User, list[str]]`, `change_password(db, ctx, current, new, meta, now)`, `logout(db, ctx, meta, now)`, `list_sessions(db, ctx) -> list[SessionOut]`, `revoke_own_session(db, ctx, session_id, meta, now)`, `issue_backup_codes(db, user_id) -> list[str]`.
  - `app.auth.schemas`: `LoginIn`, `LoginOut`, `MfaIn`, `MfaTokenIn`, `EnrollStartOut`, `MeOut`, `EnrollConfirmOut`, `PasswordChangeIn`, `SessionOut`, `me_out(ctx) -> MeOut`.
  - HTTP: `POST /auth/login`, `POST /auth/2fa/verify`, `POST /auth/2fa/enroll/start`, `POST /auth/2fa/enroll/confirm`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/password/change`, `GET /auth/sessions`, `DELETE /auth/sessions/{session_id}`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_auth_api.py`:
```python
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, update

from app.auth.context import CSRF_COOKIE, CSRF_HEADER
from app.auth.models import User
from app.core.db import get_engine, new_session
from app.main import create_app
from tests.helpers import DEFAULT_PASSWORD, SeedUser, login

NEW_PASSWORD = "Yangi-Mustahkam-77#"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


def _login_step(client: TestClient, username: str, password: str = DEFAULT_PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def _audit_actions(user_id: int) -> list[str]:
    with get_engine("app").connect() as conn:
        return list(
            conn.execute(
                text("SELECT action FROM core.audit_log WHERE user_id = :u ORDER BY id"),
                {"u": user_id},
            ).scalars()
        )


def test_unknown_user_is_generic_401(client: TestClient) -> None:
    r = _login_step(client, "no_such_user")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_full_login_sets_hardened_cookies(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user("economist_filiala", branch_ids=(4,))
    r = _login_step(client, user.username)
    assert r.status_code == 200 and r.json()["next"] == "mfa_verify"
    r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": r.json()["mfa_token"], "code": user.next_code()})
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("__Host-ugk_session="))
    for attr in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert attr.lower() in session_cookie.lower()
    assert any(c.startswith("__Host-ugk_csrf=") for c in cookies)
    body = r.json()
    assert body["username"] == user.username
    assert body["branch_ids"] == [4]
    assert "section:kazna:view" in body["permissions"]
    assert _audit_actions(user.id)[-2:] == ["auth.password.ok", "auth.login.ok"]


def test_login_username_is_normalized(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    r = _login_step(client, f"  {user.username.upper()} ")
    assert r.status_code == 200


def test_lockout_after_five_failures(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    for _ in range(5):
        assert _login_step(client, user.username, "Wrong-Password-1!").status_code == 401
    assert _login_step(client, user.username).status_code == 401  # to'g'ri parol ham rad
    with new_session() as s:
        s.execute(update(User).where(User.id == user.id).values(locked_until=datetime.now(UTC) - timedelta(seconds=1)))
        s.commit()
    assert _login_step(client, user.username).status_code == 200


def test_inactive_user_cannot_login(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    with new_session() as s:
        s.execute(update(User).where(User.id == user.id).values(is_active=False))
        s.commit()
    assert _login_step(client, user.username).json()["error"]["code"] == "invalid_credentials"


def test_challenge_dies_after_five_wrong_codes(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    token = _login_step(client, user.username).json()["mfa_token"]
    for _ in range(5):
        r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": "000000"})
        assert r.json()["error"]["code"] == "invalid_mfa_code"
    r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": user.next_code()})
    assert r.json()["error"]["code"] == "mfa_expired"


def test_totp_code_cannot_be_replayed(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    code = user.next_code()
    t1 = _login_step(client, user.username).json()["mfa_token"]
    assert client.post("/api/v1/auth/2fa/verify", json={"mfa_token": t1, "code": code}).status_code == 200
    t2 = _login_step(client, user.username).json()["mfa_token"]
    r = client.post("/api/v1/auth/2fa/verify", json={"mfa_token": t2, "code": code})
    assert r.json()["error"]["code"] == "invalid_mfa_code"


def test_enroll_flow_and_backup_codes(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user(totp=False)
    r = _login_step(client, user.username)
    assert r.json()["next"] == "mfa_enroll"
    token = r.json()["mfa_token"]
    # verify-turdagi endpoint enroll tokenini qabul qilmaydi
    assert client.post("/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": "123456"}).json()["error"]["code"] == "mfa_expired"
    start = client.post("/api/v1/auth/2fa/enroll/start", json={"mfa_token": token}).json()
    assert start["otpauth_uri"].startswith("otpauth://totp/UGEKAZNA:")
    assert start["qr_svg_data_uri"].startswith("data:image/svg+xml")
    otp = pyotp.TOTP(start["secret"])
    bad = client.post("/api/v1/auth/2fa/enroll/confirm", json={"mfa_token": token, "code": "000000"})
    assert bad.json()["error"]["code"] == "invalid_mfa_code"
    ok = client.post("/api/v1/auth/2fa/enroll/confirm", json={"mfa_token": token, "code": otp.now()})
    assert ok.status_code == 200
    codes = ok.json()["backup_codes"]
    assert len(codes) == 10
    assert "auth.mfa.enrolled" in _audit_actions(user.id)

    # Endi login verify'ga olib boradi; zaxira kod bir marta ishlaydi.
    fresh = TestClient(client.app, base_url="https://testserver")
    t = _login_step(fresh, user.username).json()
    assert t["next"] == "mfa_verify"
    assert fresh.post("/api/v1/auth/2fa/verify", json={"mfa_token": t["mfa_token"], "code": codes[0].lower()}).status_code == 200
    t = _login_step(fresh, user.username).json()
    assert fresh.post("/api/v1/auth/2fa/verify", json={"mfa_token": t["mfa_token"], "code": codes[0]}).status_code == 401


def test_me_and_logout(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    login(client, user)
    assert client.get("/api/v1/auth/me").json()["username"] == user.username
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_forced_password_change(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user(must_change=True)
    login(client, user)
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is True
    assert client.get("/api/v1/auth/sessions").json()["error"]["code"] == "password_change_required"

    weak = client.post("/api/v1/auth/password/change", json={"current_password": DEFAULT_PASSWORD, "new_password": "short"})
    assert weak.status_code == 422
    assert "password_too_short" in weak.json()["error"]["params"]["problems"]

    wrong = client.post("/api/v1/auth/password/change", json={"current_password": "Nope-Nope-123!", "new_password": NEW_PASSWORD})
    assert wrong.json()["error"]["code"] == "invalid_current_password"

    same = client.post("/api/v1/auth/password/change", json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD})
    assert same.json()["error"]["params"]["problems"] == ["password_reused"]

    other = TestClient(client.app, base_url="https://testserver")
    login(other, user)
    ok = client.post("/api/v1/auth/password/change", json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD})
    assert ok.status_code == 204
    assert client.get("/api/v1/auth/sessions").status_code == 200  # joriy sessiya tirik
    assert other.get("/api/v1/auth/me").status_code == 401  # boshqasi bekor
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is False


def test_sessions_list_and_revoke(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    user = make_user()
    other = TestClient(client.app, base_url="https://testserver")
    login(other, user)
    login(client, user)
    listed = client.get("/api/v1/auth/sessions").json()
    assert len(listed) >= 2
    current = [s for s in listed if s["current"]]
    assert len(current) == 1 and current[0]["ip"] == "testclient"
    victim = next(s for s in listed if not s["current"])
    assert client.delete(f"/api/v1/auth/sessions/{victim['id']}").status_code == 204
    assert other.get("/api/v1/auth/me").status_code == 401


def test_cannot_revoke_foreign_session(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    a, b = make_user(), make_user()
    other = TestClient(client.app, base_url="https://testserver")
    login(other, b)
    b_session = other.get("/api/v1/auth/sessions").json()[0]["id"]
    login(client, a)
    assert client.delete(f"/api/v1/auth/sessions/{b_session}").status_code == 404


def test_csrf_header_required_for_logout(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user())
    del client.headers[CSRF_HEADER]
    assert client.post("/api/v1/auth/logout").status_code == 403
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    assert client.post("/api/v1/auth/logout").status_code == 204
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_auth_api.py -v`
Expected: FAIL — 404 (`/api/v1/auth/login` yo'q).

- [ ] **Step 3: Implementatsiya**

`backend/app/auth/schemas.py`:
```python
"""Auth API sxemalari. Kirishda noma'lum maydonlar rad etiladi."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.auth.context import AuthContext


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(_In):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginOut(BaseModel):
    next: Literal["mfa_verify", "mfa_enroll"]
    mfa_token: str


class MfaTokenIn(_In):
    mfa_token: str = Field(min_length=20, max_length=128)


class MfaIn(MfaTokenIn):
    code: str = Field(min_length=6, max_length=16)


class EnrollStartOut(BaseModel):
    otpauth_uri: str
    qr_svg_data_uri: str
    secret: str


class MeOut(BaseModel):
    id: int
    username: str
    full_name: str
    role_code: str
    permissions: list[str]
    branch_ids: list[int] | None
    must_change_password: bool


class EnrollConfirmOut(BaseModel):
    user: MeOut
    backup_codes: list[str]


class PasswordChangeIn(_In):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    ua_summary: str
    ip: str | None
    current: bool


def me_out(ctx: AuthContext) -> MeOut:
    return MeOut(
        id=ctx.user_id,
        username=ctx.username,
        full_name=ctx.full_name,
        role_code=ctx.role_code,
        permissions=sorted(ctx.permissions),
        branch_ids=None if ctx.branch_ids is None else sorted(ctx.branch_ids),
        must_change_password=ctx.must_change_password,
    )
```

`backend/app/auth/service.py`:
```python
"""Autentifikatsiya oqimlari (spec 3.1): parol → 2FA challenge → sessiya."""

from __future__ import annotations

import secrets
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, NoReturn

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, log_event
from app.auth import passwords, sessions, totp
from app.auth.context import AuthContext
from app.auth.models import BackupCode, MfaChallenge, PasswordHistory, User, UserSession
from app.auth.schemas import SessionOut
from app.core import keystore, ratelimit
from app.core.config import get_settings
from app.core.crypto import CryptoError, Purpose, keyed_hash
from app.core.errors import AuthError, ConflictError, NotFoundError, ValidationFailed
from app.core.request_meta import ClientMeta

MFA_CHALLENGE_TTL = timedelta(minutes=5)
MFA_MAX_ATTEMPTS = 5


@dataclass(frozen=True, slots=True)
class LoginResult:
    next: Literal["mfa_verify", "mfa_enroll"]
    mfa_token: str


@dataclass(frozen=True, slots=True)
class EnrollStart:
    otpauth_uri: str
    qr_svg_data_uri: str
    secret: str


def normalize_username(raw: str) -> str:
    return unicodedata.normalize("NFKC", raw).strip().lower()


def totp_aad(user_id: int) -> str:
    return f"core.users.totp_secret_enc:{user_id}"


def _challenge_hmac(token: str) -> bytes:
    return keyed_hash(keystore.pepper(), "mfa", token)


def _backup_hmac(user_id: int, normalized: str) -> bytes:
    return keyed_hash(keystore.pepper(), "backup", f"{user_id}:{normalized}")


def login(db: Session, username: str, password: str, meta: ClientMeta, now: datetime) -> LoginResult:
    settings = get_settings()
    ratelimit.check("login_ip", meta.ip or "unknown", ratelimit.LOGIN_PER_IP)
    uname = normalize_username(username)
    user = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
    if user is None:
        passwords.dummy_verify(password)
        log_event(meta, AuditAction.LOGIN_FAIL, user_id=None, result="fail",
                  details={"username": uname[:64], "reason": "unknown_user"})
        raise AuthError("invalid_credentials")

    password_ok = passwords.verify_password(password, user.password_hash)
    locked = user.locked_until is not None and user.locked_until > now
    if not user.is_active or locked or not password_ok:
        reason = "inactive" if not user.is_active else "locked" if locked else "bad_password"
        if reason == "bad_password":
            user.failed_logins += 1
            if user.failed_logins >= settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_logins = 0
                reason = "locked_now"
            db.commit()  # so'rov rollback bo'lsa ham hisoblagich saqlanadi
        log_event(meta, AuditAction.LOGIN_FAIL, user_id=user.id, result="fail",
                  details={"reason": reason})
        raise AuthError("invalid_credentials")

    user.failed_logins = 0
    user.locked_until = None
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    kind: Literal["verify", "enroll"] = "verify" if user.totp_enabled else "enroll"
    token = secrets.token_urlsafe(32)
    db.add(
        MfaChallenge(
            token_hmac=_challenge_hmac(token),
            user_id=user.id,
            kind=kind,
            created_at=now,
            expires_at=now + MFA_CHALLENGE_TTL,
        )
    )
    db.flush()
    log_event(meta, AuditAction.PASSWORD_OK, user_id=user.id)
    return LoginResult(next="mfa_verify" if kind == "verify" else "mfa_enroll", mfa_token=token)


def _load_challenge(db: Session, token: str, kind: str, now: datetime) -> tuple[MfaChallenge, User]:
    challenge = db.execute(
        select(MfaChallenge).where(MfaChallenge.token_hmac == _challenge_hmac(token)).with_for_update()
    ).scalar_one_or_none()
    if (
        challenge is None
        or challenge.kind != kind
        or challenge.used_at is not None
        or challenge.expires_at <= now
        or challenge.attempts >= MFA_MAX_ATTEMPTS
    ):
        raise AuthError("mfa_expired")
    user = db.get(User, challenge.user_id)
    if user is None or not user.is_active:
        raise AuthError("mfa_expired")
    return challenge, user


def _fail_attempt(db: Session, challenge: MfaChallenge, user: User, meta: ClientMeta) -> NoReturn:
    challenge.attempts += 1
    db.commit()
    log_event(meta, AuditAction.MFA_FAIL, user_id=user.id, result="fail",
              details={"attempts": challenge.attempts})
    raise AuthError("invalid_mfa_code")


def _consume_backup_code(db: Session, user_id: int, code: str, now: datetime) -> bool:
    normalized = totp.normalize_backup_code(code)
    if normalized is None:
        return False
    row = db.execute(
        select(BackupCode)
        .where(
            BackupCode.user_id == user_id,
            BackupCode.code_hmac == _backup_hmac(user_id, normalized),
            BackupCode.used_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        return False
    row.used_at = now
    return True


def issue_backup_codes(db: Session, user_id: int) -> list[str]:
    db.execute(delete(BackupCode).where(BackupCode.user_id == user_id))
    codes = totp.generate_backup_codes()
    for code in codes:
        normalized = totp.normalize_backup_code(code)
        assert normalized is not None
        db.add(BackupCode(user_id=user_id, code_hmac=_backup_hmac(user_id, normalized)))
    return codes


def _decrypt_secret(user: User) -> str | None:
    if user.totp_secret_enc is None:
        return None
    try:
        return keystore.decrypt_str(Purpose.MFA, user.totp_secret_enc, totp_aad(user.id))
    except CryptoError:
        return None


def verify_mfa(
    db: Session, token: str, code: str, meta: ClientMeta, now: datetime
) -> tuple[sessions.NewSession, User]:
    ratelimit.check("mfa_ip", meta.ip or "unknown", ratelimit.MFA_PER_IP)
    challenge, user = _load_challenge(db, token, "verify", now)
    secret = _decrypt_secret(user)
    step = totp.verify(secret, code, user.totp_last_step, now.timestamp()) if secret else None
    used_backup = False
    if step is not None:
        user.totp_last_step = step
    else:
        used_backup = _consume_backup_code(db, user.id, code, now)
        if not used_backup:
            _fail_attempt(db, challenge, user, meta)
    challenge.used_at = now
    user.last_login_at = now
    new = sessions.create(db, user.id, meta.ip, meta.ua, now)
    if used_backup:
        log_event(meta, AuditAction.BACKUP_CODE_USED, user_id=user.id)
    log_event(meta, AuditAction.LOGIN_OK, user_id=user.id,
              details={"method": "backup_code" if used_backup else "totp"})
    return new, user


def enroll_start(db: Session, token: str, now: datetime) -> EnrollStart:
    _challenge, user = _load_challenge(db, token, "enroll", now)
    if user.totp_enabled:
        raise ConflictError("mfa_already_enabled")
    secret = totp.new_secret()
    user.totp_secret_enc = keystore.encrypt_str(Purpose.MFA, secret, totp_aad(user.id))
    uri = totp.provisioning_uri(secret, user.username)
    return EnrollStart(otpauth_uri=uri, qr_svg_data_uri=totp.qr_data_uri(uri), secret=secret)


def enroll_confirm(
    db: Session, token: str, code: str, meta: ClientMeta, now: datetime
) -> tuple[sessions.NewSession, User, list[str]]:
    ratelimit.check("mfa_ip", meta.ip or "unknown", ratelimit.MFA_PER_IP)
    challenge, user = _load_challenge(db, token, "enroll", now)
    if user.totp_enabled:
        raise ConflictError("mfa_already_enabled")
    secret = _decrypt_secret(user)
    if secret is None:
        raise AuthError("mfa_expired")
    step = totp.verify(secret, code, None, now.timestamp())
    if step is None:
        _fail_attempt(db, challenge, user, meta)
    user.totp_enabled = True
    user.totp_last_step = step
    codes = issue_backup_codes(db, user.id)
    challenge.used_at = now
    user.last_login_at = now
    new = sessions.create(db, user.id, meta.ip, meta.ua, now)
    log_event(meta, AuditAction.MFA_ENROLLED, user_id=user.id)
    log_event(meta, AuditAction.LOGIN_OK, user_id=user.id, details={"method": "totp_enroll"})
    return new, user, codes


def change_password(
    db: Session, ctx: AuthContext, current: str, new: str, meta: ClientMeta, now: datetime
) -> None:
    user = db.get(User, ctx.user_id, with_for_update=True)
    if user is None:
        raise AuthError("session_expired")
    if not passwords.verify_password(current, user.password_hash):
        log_event(meta, AuditAction.PASSWORD_CHANGE_FAIL, user_id=user.id, result="fail")
        raise ValidationFailed("invalid_current_password")
    history = [
        user.password_hash,
        *db.execute(
            select(PasswordHistory.password_hash)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())
            .limit(passwords.HISTORY_DEPTH - 1)
        ).scalars(),
    ]
    problems = passwords.policy_problems(new, username=user.username, previous_hashes=history)
    if problems:
        raise ValidationFailed("password_policy", problems=problems)
    db.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash, created_at=now))
    db.flush()
    keep = select(PasswordHistory.id).where(PasswordHistory.user_id == user.id).order_by(
        PasswordHistory.created_at.desc(), PasswordHistory.id.desc()
    ).limit(passwords.HISTORY_DEPTH - 1)
    db.execute(
        delete(PasswordHistory).where(
            PasswordHistory.user_id == user.id, PasswordHistory.id.not_in(keep.scalar_subquery())
        )
    )
    user.password_hash = passwords.hash_password(new)
    user.password_changed_at = now
    user.must_change_password = False
    sessions.revoke_all(db, user.id, "password_changed", now, except_id=ctx.session_id)
    log_event(meta, AuditAction.PASSWORD_CHANGED, user_id=user.id)


def logout(db: Session, ctx: AuthContext, meta: ClientMeta, now: datetime) -> None:
    sessions.revoke(db, ctx.session_id, "logout", now)
    log_event(meta, AuditAction.LOGOUT, user_id=ctx.user_id)


def list_sessions(db: Session, ctx: AuthContext) -> list[SessionOut]:
    rows = db.execute(
        select(UserSession)
        .where(UserSession.user_id == ctx.user_id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_seen_at.desc())
    ).scalars()
    out: list[SessionOut] = []
    for row in rows:
        ip: str | None = None
        if row.ip_enc is not None:
            try:
                ip = keystore.decrypt_str(Purpose.PII, row.ip_enc, sessions.ip_aad(row.id))
            except CryptoError:
                ip = None
        out.append(
            SessionOut(
                id=row.id,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                ua_summary=row.ua_summary,
                ip=ip,
                current=row.id == ctx.session_id,
            )
        )
    return out


def revoke_own_session(
    db: Session, ctx: AuthContext, session_id: uuid.UUID, meta: ClientMeta, now: datetime
) -> None:
    row = db.get(UserSession, session_id)
    if row is None or row.user_id != ctx.user_id:
        raise NotFoundError()
    sessions.revoke(db, session_id, "user_revoked", now)
    log_event(meta, AuditAction.SESSION_REVOKED, user_id=ctx.user_id,
              object_type="session", object_id=session_id)
```

`backend/app/auth/router.py`:
```python
"""Auth endpointlari."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.context import CSRF_COOKIE, SESSION_COOKIE, Ctx, build_context
from app.auth.schemas import (
    EnrollConfirmOut,
    EnrollStartOut,
    LoginIn,
    LoginOut,
    MeOut,
    MfaIn,
    MfaTokenIn,
    PasswordChangeIn,
    SessionOut,
    me_out,
)
from app.auth.sessions import NewSession
from app.core.db import get_db
from app.core.request_meta import Meta

router = APIRouter(prefix="/auth", tags=["auth"])
DB = Annotated[Session, Depends(get_db)]


def _set_session_cookies(response: Response, new: NewSession) -> None:
    response.set_cookie(SESSION_COOKIE, new.token, httponly=True, secure=True, samesite="strict", path="/")
    response.set_cookie(CSRF_COOKIE, new.csrf, httponly=False, secure=True, samesite="strict", path="/")


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=True, samesite="strict")


@router.post("/login")
def login(body: LoginIn, db: DB, meta: Meta) -> LoginOut:
    result = service.login(db, body.username, body.password, meta, datetime.now(UTC))
    return LoginOut(next=result.next, mfa_token=result.mfa_token)


@router.post("/2fa/verify")
def verify(body: MfaIn, response: Response, db: DB, meta: Meta) -> MeOut:
    now = datetime.now(UTC)
    new, user = service.verify_mfa(db, body.mfa_token, body.code, meta, now)
    _set_session_cookies(response, new)
    return me_out(build_context(db, user, new.id, now))


@router.post("/2fa/enroll/start")
def enroll_start(body: MfaTokenIn, db: DB) -> EnrollStartOut:
    start = service.enroll_start(db, body.mfa_token, datetime.now(UTC))
    return EnrollStartOut(
        otpauth_uri=start.otpauth_uri, qr_svg_data_uri=start.qr_svg_data_uri, secret=start.secret
    )


@router.post("/2fa/enroll/confirm")
def enroll_confirm(body: MfaIn, response: Response, db: DB, meta: Meta) -> EnrollConfirmOut:
    now = datetime.now(UTC)
    new, user, codes = service.enroll_confirm(db, body.mfa_token, body.code, meta, now)
    _set_session_cookies(response, new)
    return EnrollConfirmOut(user=me_out(build_context(db, user, new.id, now)), backup_codes=codes)


@router.post("/logout", status_code=204)
def logout(ctx: Ctx, db: DB, meta: Meta) -> Response:
    service.logout(db, ctx, meta, datetime.now(UTC))
    response = Response(status_code=204)
    _clear_cookies(response)
    return response


@router.get("/me")
def me(ctx: Ctx) -> MeOut:
    return me_out(ctx)


@router.post("/password/change", status_code=204)
def change_password(body: PasswordChangeIn, ctx: Ctx, db: DB, meta: Meta) -> Response:
    service.change_password(db, ctx, body.current_password, body.new_password, meta, datetime.now(UTC))
    return Response(status_code=204)


@router.get("/sessions")
def list_sessions(ctx: Ctx, db: DB) -> list[SessionOut]:
    return service.list_sessions(db, ctx)


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: uuid.UUID, ctx: Ctx, db: DB, meta: Meta) -> Response:
    service.revoke_own_session(db, ctx, session_id, meta, datetime.now(UTC))
    return Response(status_code=204)
```

`backend/app/main.py` — import va `include_router` qo'shing:
```python
from app.auth.router import router as auth_router
```
```python
    app.include_router(auth_router, prefix=API_PREFIX)
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(auth): login, TOTP 2FA (verify/enroll), zaxira kodlar, parol almashtirish, sessiyalar API"
```

---

### Task 11: Admin API — foydalanuvchilar, lavozimlar, rollar; deny-by-default route testi

**Files:**
- Create: `backend/app/admin/__init__.py`, `backend/app/admin/schemas.py`, `backend/app/admin/service.py`, `backend/app/admin/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_admin_api.py`, `backend/tests/test_route_guards.py`

**Interfaces:**
- Consumes: `require_perm`, `Perm`, `AuthContext`, `passwords`, `sessions.revoke_all`, `log_event`, `AuditAction`, modellar, `service.normalize_username`.
- Produces: `app.admin.schemas`: `Page[T]`, `UserCreate`, `UserUpdate`, `UserOut`, `PositionRef`, `UserCreated`, `TemporaryPassword`, `RoleIn`, `RoleUpdate`, `RoleOut`, `PositionIn`, `PositionUpdate`, `PositionOut`, `PermissionOut`. `app.admin.service`: `list_users`, `get_user_out`, `create_user`, `update_user`, `set_active`, `reset_password`, `reset_mfa`, `list_roles`, `create_role`, `update_role`, `list_positions`, `create_position`, `update_position`, `list_permissions`, `assert_admin_remains`. HTTP: `/admin/users` (GET, POST), `/admin/users/{id}` (PATCH), `/admin/users/{id}/block|unblock|reset-password|reset-2fa` (POST), `/admin/permissions` (GET), `/admin/roles` (GET, POST), `/admin/roles/{id}` (PATCH), `/admin/positions` (GET, POST), `/admin/positions/{id}` (PATCH).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_route_guards.py`:
```python
from collections.abc import Iterator

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.auth.context import get_ctx
from app.main import create_app

PUBLIC = {
    ("GET", "/api/v1/healthz"),
    ("GET", "/api/v1/readyz"),
    ("GET", "/api/v1/openapi.json"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/2fa/verify"),
    ("POST", "/api/v1/auth/2fa/enroll/start"),
    ("POST", "/api/v1/auth/2fa/enroll/confirm"),
}
PREFIX_PERMS = {"/api/v1/admin/": "admin:", "/api/v1/audit": "audit:read"}


def _calls(dep: Dependant) -> Iterator[object]:
    for sub in dep.dependencies:
        yield sub.call
        yield from _calls(sub)


def _routes() -> Iterator[tuple[str, APIRoute]]:
    for route in create_app().routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                yield method, route


def test_every_non_public_route_requires_session() -> None:
    for method, route in _routes():
        if (method, route.path) in PUBLIC:
            continue
        assert get_ctx in set(_calls(route.dependant)), f"{method} {route.path} himoyasiz"


def test_admin_and_audit_routes_require_matching_permission() -> None:
    for method, route in _routes():
        for prefix, needed in PREFIX_PERMS.items():
            if not route.path.startswith(prefix):
                continue
            perms: set[str] = set()
            for call in _calls(route.dependant):
                perms |= set(getattr(call, "required_perms", ()))
            assert any(p.startswith(needed) for p in perms), f"{method} {route.path}: {perms}"


def test_all_protected_routes_return_401_without_session() -> None:
    with TestClient(create_app(), base_url="https://testserver") as client:
        for method, route in _routes():
            if (method, route.path) in PUBLIC:
                continue
            path = route.path.replace("{user_id}", "1").replace("{role_id}", "1").replace(
                "{position_id}", "1").replace("{session_id}", "00000000-0000-0000-0000-000000000000"
            ).replace("{purpose}", "mfa")
            response = client.request(method, path, json={})
            assert response.status_code == 401, f"{method} {path}: {response.status_code}"
```

`backend/tests/test_admin_api.py`:
```python
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.admin import service as admin_service
from app.auth.context import AuthContext
from app.auth.models import Position, Role, User
from app.core.db import get_engine, new_session
from app.core.errors import ConflictError
from app.core.request_meta import ClientMeta
from app.main import create_app
from tests.helpers import SeedUser, login


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


@pytest.fixture
def admin(client: TestClient, make_user: Callable[..., SeedUser]) -> SeedUser:
    user = make_user("admin")
    login(client, user)
    return user


def _position_id(code: str) -> int:
    with new_session() as s:
        return s.execute(select(Position.id).where(Position.code == code)).scalar_one()


def _new_username() -> str:
    return f"new.{uuid.uuid4().hex[:8]}"


def test_non_admin_forbidden(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("rukovodstvo"))
    assert client.get("/api/v1/admin/users").status_code == 403


@pytest.mark.usefixtures("admin")
def test_create_user_and_first_login_requires_enroll(client: TestClient) -> None:
    username = _new_username()
    r = client.post("/api/v1/admin/users", json={
        "username": f"  {username.upper()} ", "full_name": "Иванов И.И.",
        "position_id": _position_id("spec_kazna")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["username"] == username
    assert body["user"]["role_code"] == "spec_kazna"
    fresh = TestClient(client.app, base_url="https://testserver")
    step = fresh.post("/api/v1/auth/login", json={"username": username, "password": body["temporary_password"]})
    assert step.json()["next"] == "mfa_enroll"
    with get_engine("app").connect() as conn:
        actions = conn.execute(text(
            "SELECT action FROM core.audit_log WHERE object_type = 'user' AND object_id = :i"),
            {"i": str(body["user"]["id"])}).scalars().all()
    assert "admin.user.created" in actions


@pytest.mark.usefixtures("admin")
def test_duplicate_username_case_insensitive(client: TestClient) -> None:
    username = _new_username()
    payload = {"username": username, "full_name": "A", "position_id": _position_id("rukovodstvo")}
    assert client.post("/api/v1/admin/users", json=payload).status_code == 201
    payload["username"] = username.upper()
    r = client.post("/api/v1/admin/users", json=payload)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "username_taken"


@pytest.mark.usefixtures("admin")
def test_invalid_username_rejected(client: TestClient) -> None:
    r = client.post("/api/v1/admin/users", json={
        "username": "bad name!", "full_name": "A", "position_id": _position_id("rukovodstvo")})
    assert r.status_code == 422


def test_block_revokes_sessions(client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]) -> None:
    victim = make_user("rukovodstvo")
    victim_client = TestClient(client.app, base_url="https://testserver")
    login(victim_client, victim)
    r = client.post(f"/api/v1/admin/users/{victim.id}/block")
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert victim_client.get("/api/v1/auth/me").status_code == 401
    step = victim_client.post("/api/v1/auth/login", json={"username": victim.username, "password": victim.password})
    assert step.status_code == 401
    assert client.post(f"/api/v1/admin/users/{victim.id}/unblock").json()["is_active"] is True


def test_cannot_block_self(client: TestClient, admin: SeedUser) -> None:
    r = client.post(f"/api/v1/admin/users/{admin.id}/block")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "cannot_modify_self"


def test_last_admin_is_protected(db: Session, make_user: Callable[..., SeedUser]) -> None:
    actor_user, target = make_user("admin"), make_user("admin")
    db.execute(update(User).where(User.id.not_in([actor_user.id, target.id])).values(is_active=False))
    actor = AuthContext(user_id=actor_user.id, username=actor_user.username, full_name="A",
                        role_code="admin", permissions=frozenset({"admin:users"}), branch_ids=None,
                        session_id=uuid.uuid4())
    meta = ClientMeta(ip=None, ua=None, request_id=None)
    db.execute(update(User).where(User.id == actor_user.id).values(is_active=False))
    with pytest.raises(ConflictError) as exc:
        admin_service.set_active(db, actor, target.id, False, meta)
    assert exc.value.code == "last_admin"


def test_reset_password_and_2fa(client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]) -> None:
    victim = make_user("rukovodstvo")
    temp = client.post(f"/api/v1/admin/users/{victim.id}/reset-password").json()["temporary_password"]
    assert client.post(f"/api/v1/admin/users/{victim.id}/reset-2fa").status_code == 204
    fresh = TestClient(client.app, base_url="https://testserver")
    assert fresh.post("/api/v1/auth/login", json={"username": victim.username, "password": victim.password}).status_code == 401
    step = fresh.post("/api/v1/auth/login", json={"username": victim.username, "password": temp})
    assert step.json()["next"] == "mfa_enroll"


def test_change_position_revokes_sessions(client: TestClient, admin: SeedUser, make_user: Callable[..., SeedUser]) -> None:
    victim = make_user("rukovodstvo")
    victim_client = TestClient(client.app, base_url="https://testserver")
    login(victim_client, victim)
    r = client.patch(f"/api/v1/admin/users/{victim.id}", json={"position_id": _position_id("spec_kazna")})
    assert r.status_code == 200 and r.json()["role_code"] == "spec_kazna"
    assert victim_client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.usefixtures("admin")
def test_roles_crud_and_admin_protection(client: TestClient) -> None:
    code = f"r_{uuid.uuid4().hex[:6]}"
    r = client.post("/api/v1/admin/roles", json={
        "code": code, "name": "Служба закупок", "scope_all": True,
        "permissions": ["section:obzor:view", "section:zakupki:view"]})
    assert r.status_code == 201
    role_id = r.json()["id"]
    assert client.post("/api/v1/admin/roles", json={
        "code": f"x_{uuid.uuid4().hex[:6]}", "name": "X", "scope_all": True,
        "permissions": ["no:such"]}).json()["error"]["code"] == "unknown_permission"
    upd = client.patch(f"/api/v1/admin/roles/{role_id}", json={"permissions": ["section:obzor:view"]})
    assert upd.json()["permissions"] == ["section:obzor:view"]
    admin_role = next(x for x in client.get("/api/v1/admin/roles").json() if x["code"] == "admin")
    r = client.patch(f"/api/v1/admin/roles/{admin_role['id']}", json={"permissions": ["section:obzor:view"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "admin_role_protected"


@pytest.mark.usefixtures("admin")
def test_positions_with_branches(client: TestClient) -> None:
    with new_session() as s:
        econ_id = s.execute(select(Role.id).where(Role.code == "economist_filiala")).scalar_one()
    code = f"econ_{uuid.uuid4().hex[:6]}"
    r = client.post("/api/v1/admin/positions", json={
        "code": code, "name": "Экономист Чарвакской ГЭС", "role_id": econ_id, "branch_ids": [2, 1]})
    assert r.status_code == 201
    assert r.json()["branch_ids"] == [1, 2]
    pid = r.json()["id"]
    r = client.patch(f"/api/v1/admin/positions/{pid}", json={"branch_ids": [5]})
    assert r.json()["branch_ids"] == [5]
    assert any(p["code"] == code for p in client.get("/api/v1/admin/positions").json())


@pytest.mark.usefixtures("admin")
def test_permissions_and_user_search(client: TestClient) -> None:
    perms = client.get("/api/v1/admin/permissions").json()
    assert {"code": "audit:read", "description": "Просмотр журнала аудита"} in perms
    page = client.get("/api/v1/admin/users", params={"q": "u", "page_size": 5}).json()
    assert page["page_size"] == 5 and len(page["items"]) <= 5 and page["total"] >= 1
    assert client.get("/api/v1/admin/users", params={"page_size": 501}).status_code == 422
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_admin_api.py tests/test_route_guards.py -v`
Expected: FAIL — admin testlari 404; `test_route_guards` hozircha o'tishi mumkin (admin route'lari yo'q) — bu normal.

- [ ] **Step 3: Implementatsiya**

`backend/app/admin/__init__.py`: bo'sh fayl.

`backend/app/admin/schemas.py`:
```python
"""Admin API sxemalari."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.service import normalize_username

T = TypeVar("T")
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,64}$")
CODE_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
BranchId = Annotated[int, Field(gt=0, lt=100000)]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UserCreate(_In):
    username: str = Field(min_length=3, max_length=80)
    full_name: str = Field(min_length=1, max_length=200)
    position_id: int = Field(gt=0)

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        normalized = normalize_username(value)
        if not USERNAME_RE.match(normalized):
            raise ValueError("username format")
        return normalized


class UserUpdate(_In):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    position_id: int | None = Field(default=None, gt=0)


class PositionRef(BaseModel):
    id: int
    code: str
    name: str


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    position: PositionRef
    role_code: str
    is_active: bool
    totp_enabled: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class UserCreated(BaseModel):
    user: UserOut
    temporary_password: str


class TemporaryPassword(BaseModel):
    temporary_password: str


class RoleIn(_In):
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    scope_all: bool
    permissions: list[str] = Field(default_factory=list, max_length=100)


class RoleUpdate(_In):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    scope_all: bool | None = None
    permissions: list[str] | None = Field(default=None, max_length=100)


class RoleOut(BaseModel):
    id: int
    code: str
    name: str
    scope_all: bool
    is_system: bool
    permissions: list[str]


class PositionIn(_In):
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    role_id: int = Field(gt=0)
    branch_ids: list[BranchId] = Field(default_factory=list, max_length=100)


class PositionUpdate(_In):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role_id: int | None = Field(default=None, gt=0)
    branch_ids: list[BranchId] | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class PositionOut(BaseModel):
    id: int
    code: str
    name: str
    role_id: int
    role_code: str
    is_active: bool
    branch_ids: list[int]


class PermissionOut(BaseModel):
    code: str
    description: str
```

`backend/app/admin/service.py`:
```python
"""Admin amallari. Har o'zgarish auditga yoziladi; kamida bitta faol administrator qoladi."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.schemas import (
    PermissionOut,
    PositionIn,
    PositionOut,
    PositionRef,
    PositionUpdate,
    RoleIn,
    RoleOut,
    RoleUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.audit.service import AuditAction, log_event
from app.auth import passwords, sessions
from app.auth.context import AuthContext
from app.auth.models import BackupCode, Permission, Position, PositionBranch, Role, RolePermission, User
from app.auth.permissions import ADMIN_GUARANTEED, ADMIN_ROLE, Perm
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.request_meta import ClientMeta


def _now() -> datetime:
    return datetime.now(UTC)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def assert_admin_remains(db: Session) -> None:
    db.flush()
    count = db.execute(
        select(func.count(User.id))
        .join(Position, Position.id == User.position_id)
        .join(
            RolePermission,
            and_(
                RolePermission.role_id == Position.role_id,
                RolePermission.permission_code == Perm.ADMIN_USERS.value,
            ),
        )
        .where(User.is_active.is_(True), Position.is_active.is_(True))
    ).scalar_one()
    if count == 0:
        raise ConflictError("last_admin")


def _user_query() -> Select[tuple[User, Position, str]]:
    return (
        select(User, Position, Role.code)
        .join(Position, Position.id == User.position_id)
        .join(Role, Role.id == Position.role_id)
    )


def _to_out(user: User, position: Position, role_code: str) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        position=PositionRef(id=position.id, code=position.code, name=position.name),
        role_code=role_code,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        locked_until=user.locked_until,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


def get_user_out(db: Session, user_id: int) -> UserOut:
    db.flush()
    row = db.execute(_user_query().where(User.id == user_id)).first()
    if row is None:
        raise NotFoundError()
    user, position, role_code = row
    db.refresh(user)
    return _to_out(user, position, role_code)


def list_users(db: Session, q: str | None, page: int, page_size: int) -> tuple[list[UserOut], int]:
    query = _user_query()
    if q:
        like = f"%{_escape_like(q.strip().lower())}%"
        query = query.where(
            or_(User.username.like(like, escape="\\"), func.lower(User.full_name).like(like, escape="\\"))
        )
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(query.order_by(User.username).offset((page - 1) * page_size).limit(page_size)).all()
    return [_to_out(*row) for row in rows], int(total)


def _load_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id, with_for_update=True)
    if user is None:
        raise NotFoundError()
    return user


def _require_position(db: Session, position_id: int) -> Position:
    position = db.get(Position, position_id)
    if position is None or not position.is_active:
        raise ValidationFailed("validation_failed", fields=["position_id"])
    return position


def _not_self(actor: AuthContext, user_id: int) -> None:
    if actor.user_id == user_id:
        raise ConflictError("cannot_modify_self")


def create_user(db: Session, actor: AuthContext, data: UserCreate, meta: ClientMeta) -> tuple[UserOut, str]:
    _require_position(db, data.position_id)
    if db.execute(select(User.id).where(User.username == data.username)).first() is not None:
        raise ConflictError("username_taken")
    temporary = passwords.generate_temporary_password()
    user = User(
        username=data.username,
        full_name=data.full_name,
        position_id=data.position_id,
        password_hash=passwords.hash_password(temporary),
        password_changed_at=_now(),
        must_change_password=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("username_taken") from exc
    log_event(meta, AuditAction.USER_CREATED, user_id=actor.user_id, object_type="user",
              object_id=user.id, details={"username": user.username, "position_id": user.position_id})
    return get_user_out(db, user.id), temporary


def update_user(db: Session, actor: AuthContext, user_id: int, data: UserUpdate, meta: ClientMeta) -> UserOut:
    user = _load_user(db, user_id)
    changes: dict[str, object] = {}
    if data.full_name is not None and data.full_name != user.full_name:
        user.full_name = data.full_name
        changes["full_name"] = True
    if data.position_id is not None and data.position_id != user.position_id:
        _not_self(actor, user_id)
        _require_position(db, data.position_id)
        changes["position_id"] = [user.position_id, data.position_id]
        user.position_id = data.position_id
        sessions.revoke_all(db, user.id, "position_changed", _now())
        assert_admin_remains(db)
    if changes:
        log_event(meta, AuditAction.USER_UPDATED, user_id=actor.user_id, object_type="user",
                  object_id=user.id, details=changes)
    return get_user_out(db, user.id)


def set_active(db: Session, actor: AuthContext, user_id: int, active: bool, meta: ClientMeta) -> UserOut:
    _not_self(actor, user_id)
    user = _load_user(db, user_id)
    user.is_active = active
    if active:
        user.failed_logins = 0
        user.locked_until = None
    else:
        sessions.revoke_all(db, user.id, "blocked", _now())
        assert_admin_remains(db)
    log_event(meta, AuditAction.USER_UNBLOCKED if active else AuditAction.USER_BLOCKED,
              user_id=actor.user_id, object_type="user", object_id=user.id)
    return get_user_out(db, user.id)


def reset_password(db: Session, actor: AuthContext, user_id: int, meta: ClientMeta) -> str:
    _not_self(actor, user_id)
    user = _load_user(db, user_id)
    temporary = passwords.generate_temporary_password()
    user.password_hash = passwords.hash_password(temporary)
    user.password_changed_at = _now()
    user.must_change_password = True
    user.failed_logins = 0
    user.locked_until = None
    sessions.revoke_all(db, user.id, "password_reset", _now())
    log_event(meta, AuditAction.USER_PASSWORD_RESET, user_id=actor.user_id, object_type="user",
              object_id=user.id)
    return temporary


def reset_mfa(db: Session, actor: AuthContext, user_id: int, meta: ClientMeta) -> None:
    _not_self(actor, user_id)
    user = _load_user(db, user_id)
    user.totp_enabled = False
    user.totp_secret_enc = None
    user.totp_last_step = None
    db.execute(delete(BackupCode).where(BackupCode.user_id == user.id))
    sessions.revoke_all(db, user.id, "mfa_reset", _now())
    log_event(meta, AuditAction.USER_MFA_RESET, user_id=actor.user_id, object_type="user",
              object_id=user.id)


# ── Ruxsatlar va rollar ─────────────────────────────────────────────
def list_permissions(db: Session) -> list[PermissionOut]:
    rows = db.execute(select(Permission).order_by(Permission.code)).scalars()
    return [PermissionOut(code=p.code, description=p.description) for p in rows]


def _role_out(db: Session, role: Role) -> RoleOut:
    perms = sorted(
        db.execute(select(RolePermission.permission_code).where(RolePermission.role_id == role.id)).scalars()
    )
    return RoleOut(id=role.id, code=role.code, name=role.name, scope_all=role.scope_all,
                   is_system=role.is_system, permissions=perms)


def list_roles(db: Session) -> list[RoleOut]:
    return [_role_out(db, r) for r in db.execute(select(Role).order_by(Role.code)).scalars()]


def _validate_permissions(db: Session, codes: list[str]) -> list[str]:
    unique = sorted(set(codes))
    known = set(db.execute(select(Permission.code).where(Permission.code.in_(unique))).scalars())
    unknown = [c for c in unique if c not in known]
    if unknown:
        raise ValidationFailed("unknown_permission", permissions=unknown)
    return unique


def _set_permissions(db: Session, role_id: int, codes: list[str]) -> None:
    db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    for code in codes:
        db.add(RolePermission(role_id=role_id, permission_code=code))


def create_role(db: Session, actor: AuthContext, data: RoleIn, meta: ClientMeta) -> RoleOut:
    perms = _validate_permissions(db, data.permissions)
    if db.execute(select(Role.id).where(Role.code == data.code)).first() is not None:
        raise ConflictError("code_taken")
    role = Role(code=data.code, name=data.name, scope_all=data.scope_all, is_system=False)
    db.add(role)
    db.flush()
    _set_permissions(db, role.id, perms)
    db.flush()
    log_event(meta, AuditAction.ROLE_CREATED, user_id=actor.user_id, object_type="role",
              object_id=role.id, details={"code": role.code, "permissions": perms})
    return _role_out(db, role)


def update_role(db: Session, actor: AuthContext, role_id: int, data: RoleUpdate, meta: ClientMeta) -> RoleOut:
    role = db.get(Role, role_id, with_for_update=True)
    if role is None:
        raise NotFoundError()
    details: dict[str, object] = {}
    if data.name is not None:
        role.name = data.name
        details["name"] = data.name
    if data.scope_all is not None:
        role.scope_all = data.scope_all
        details["scope_all"] = data.scope_all
    if data.permissions is not None:
        perms = _validate_permissions(db, data.permissions)
        if role.code == ADMIN_ROLE and not ADMIN_GUARANTEED <= set(perms):
            raise ConflictError("admin_role_protected")
        _set_permissions(db, role.id, perms)
        details["permissions"] = perms
        assert_admin_remains(db)
    db.flush()
    log_event(meta, AuditAction.ROLE_UPDATED, user_id=actor.user_id, object_type="role",
              object_id=role.id, details=details)
    return _role_out(db, role)


# ── Lavozimlar ──────────────────────────────────────────────────────
def _position_out(db: Session, position: Position) -> PositionOut:
    role_code = db.execute(select(Role.code).where(Role.id == position.role_id)).scalar_one()
    branches = sorted(
        db.execute(select(PositionBranch.branch_id).where(PositionBranch.position_id == position.id)).scalars()
    )
    return PositionOut(id=position.id, code=position.code, name=position.name, role_id=position.role_id,
                       role_code=role_code, is_active=position.is_active, branch_ids=branches)


def list_positions(db: Session) -> list[PositionOut]:
    return [_position_out(db, p) for p in db.execute(select(Position).order_by(Position.code)).scalars()]


def _set_branches(db: Session, position_id: int, branch_ids: list[int]) -> None:
    db.execute(delete(PositionBranch).where(PositionBranch.position_id == position_id))
    for branch in sorted(set(branch_ids)):
        db.add(PositionBranch(position_id=position_id, branch_id=branch))


def _require_role(db: Session, role_id: int) -> None:
    if db.get(Role, role_id) is None:
        raise ValidationFailed("validation_failed", fields=["role_id"])


def create_position(db: Session, actor: AuthContext, data: PositionIn, meta: ClientMeta) -> PositionOut:
    _require_role(db, data.role_id)
    if db.execute(select(Position.id).where(Position.code == data.code)).first() is not None:
        raise ConflictError("code_taken")
    position = Position(code=data.code, name=data.name, role_id=data.role_id)
    db.add(position)
    db.flush()
    _set_branches(db, position.id, data.branch_ids)
    db.flush()
    log_event(meta, AuditAction.POSITION_CREATED, user_id=actor.user_id, object_type="position",
              object_id=position.id, details={"code": position.code, "role_id": position.role_id,
                                              "branch_ids": sorted(set(data.branch_ids))})
    return _position_out(db, position)


def update_position(db: Session, actor: AuthContext, position_id: int, data: PositionUpdate,
                    meta: ClientMeta) -> PositionOut:
    position = db.get(Position, position_id, with_for_update=True)
    if position is None:
        raise NotFoundError()
    details: dict[str, object] = {}
    scope_changed = False
    if data.name is not None:
        position.name = data.name
        details["name"] = data.name
    if data.role_id is not None and data.role_id != position.role_id:
        _require_role(db, data.role_id)
        details["role_id"] = [position.role_id, data.role_id]
        position.role_id = data.role_id
        scope_changed = True
    if data.branch_ids is not None:
        _set_branches(db, position.id, data.branch_ids)
        details["branch_ids"] = sorted(set(data.branch_ids))
        scope_changed = True
    if data.is_active is not None and data.is_active != position.is_active:
        position.is_active = data.is_active
        details["is_active"] = data.is_active
        scope_changed = True
    if scope_changed:
        now = _now()
        for user_id in db.execute(select(User.id).where(User.position_id == position.id)).scalars():
            sessions.revoke_all(db, user_id, "position_changed", now)
        assert_admin_remains(db)
    db.flush()
    log_event(meta, AuditAction.POSITION_UPDATED, user_id=actor.user_id, object_type="position",
              object_id=position.id, details=details)
    return _position_out(db, position)
```

`backend/app/admin/router.py`:
```python
"""Admin endpointlari: foydalanuvchilar (admin:users), rollar va lavozimlar (admin:roles)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.admin import service
from app.admin.schemas import (
    Page,
    PermissionOut,
    PositionIn,
    PositionOut,
    PositionUpdate,
    RoleIn,
    RoleOut,
    RoleUpdate,
    TemporaryPassword,
    UserCreate,
    UserCreated,
    UserOut,
    UserUpdate,
)
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core.db import get_db
from app.core.request_meta import Meta

router = APIRouter(prefix="/admin", tags=["admin"])
DB = Annotated[Session, Depends(get_db)]
UsersAdmin = Annotated[AuthContext, Depends(require_perm(Perm.ADMIN_USERS))]
RolesAdmin = Annotated[AuthContext, Depends(require_perm(Perm.ADMIN_ROLES))]


@router.get("/users")
def list_users(
    ctx: UsersAdmin,
    db: DB,
    q: Annotated[str | None, Query(max_length=64)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Page[UserOut]:
    items, total = service.list_users(db, q, page, page_size)
    return Page[UserOut](items=items, total=total, page=page, page_size=page_size)


@router.post("/users", status_code=201)
def create_user(body: UserCreate, ctx: UsersAdmin, db: DB, meta: Meta) -> UserCreated:
    user, temporary = service.create_user(db, ctx, body, meta)
    return UserCreated(user=user, temporary_password=temporary)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, ctx: UsersAdmin, db: DB, meta: Meta) -> UserOut:
    return service.update_user(db, ctx, user_id, body, meta)


@router.post("/users/{user_id}/block")
def block_user(user_id: int, ctx: UsersAdmin, db: DB, meta: Meta) -> UserOut:
    return service.set_active(db, ctx, user_id, False, meta)


@router.post("/users/{user_id}/unblock")
def unblock_user(user_id: int, ctx: UsersAdmin, db: DB, meta: Meta) -> UserOut:
    return service.set_active(db, ctx, user_id, True, meta)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, ctx: UsersAdmin, db: DB, meta: Meta) -> TemporaryPassword:
    return TemporaryPassword(temporary_password=service.reset_password(db, ctx, user_id, meta))


@router.post("/users/{user_id}/reset-2fa", status_code=204)
def reset_2fa(user_id: int, ctx: UsersAdmin, db: DB, meta: Meta) -> Response:
    service.reset_mfa(db, ctx, user_id, meta)
    return Response(status_code=204)


@router.get("/permissions")
def list_permissions(ctx: RolesAdmin, db: DB) -> list[PermissionOut]:
    return service.list_permissions(db)


@router.get("/roles")
def list_roles(ctx: RolesAdmin, db: DB) -> list[RoleOut]:
    return service.list_roles(db)


@router.post("/roles", status_code=201)
def create_role(body: RoleIn, ctx: RolesAdmin, db: DB, meta: Meta) -> RoleOut:
    return service.create_role(db, ctx, body, meta)


@router.patch("/roles/{role_id}")
def update_role(role_id: int, body: RoleUpdate, ctx: RolesAdmin, db: DB, meta: Meta) -> RoleOut:
    return service.update_role(db, ctx, role_id, body, meta)


@router.get("/positions")
def list_positions(ctx: RolesAdmin, db: DB) -> list[PositionOut]:
    return service.list_positions(db)


@router.post("/positions", status_code=201)
def create_position(body: PositionIn, ctx: RolesAdmin, db: DB, meta: Meta) -> PositionOut:
    return service.create_position(db, ctx, body, meta)


@router.patch("/positions/{position_id}")
def update_position(position_id: int, body: PositionUpdate, ctx: RolesAdmin, db: DB, meta: Meta) -> PositionOut:
    return service.update_position(db, ctx, position_id, body, meta)
```

`backend/app/main.py` — import va `include_router` qo'shing:
```python
from app.admin.router import router as admin_router
```
```python
    app.include_router(admin_router, prefix=API_PREFIX)
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(admin): foydalanuvchilar, rollar, lavozimlar API; deny-by-default route testlari"
```

---

### Task 12: Audit API — ro'yxat, CSV eksport, zanjirni tekshirish

**Files:**
- Create: `backend/app/audit/schemas.py`, `backend/app/audit/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_audit_api.py`

**Interfaces:**
- Consumes: `require_perm(Perm.AUDIT_READ)`, `verify_chain_snapshot`, `log_event`, `ip_aad`, `keystore.decrypt_str`, `Page`.
- Produces: HTTP `GET /audit` (`from_ts`, `to_ts`, `user_id`, `action` — prefiks, `result`, `page`, `page_size`) → `Page[AuditOut]`; `GET /audit/export.csv` → `text/csv` (BOM, `;`, formula-injection himoyasi, ≤50 000 qator); `POST /audit/verify` → `VerifyOut(ok, checked, first_bad_id)`. `app.audit.schemas.AuditOut(id, ts, user_id, username, action, result, object_type, object_id, request_id, details, ip)`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_audit_api.py`:
```python
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.audit.service import AuditAction, AuditEvent, record
from app.main import create_app
from tests.helpers import SeedUser, login


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


def test_requires_audit_permission(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("rukovodstvo"))
    assert client.get("/api/v1/audit").status_code == 403


def test_list_filters_and_decrypts_ip(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    auditor = make_user("vnutr_kontrol")
    login(client, auditor)
    record(AuditEvent(action=AuditAction.USER_BLOCKED, user_id=auditor.id, ip="172.16.5.9",
                      object_type="user", object_id="42"))
    page = client.get("/api/v1/audit", params={"user_id": auditor.id, "action": "admin.user"}).json()
    assert page["total"] >= 1
    item = page["items"][0]
    assert item["action"] == "admin.user.blocked"
    assert item["ip"] == "172.16.5.9"
    assert item["username"] == auditor.username


def test_export_csv_is_safe_and_audited(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    auditor = make_user("vnutr_kontrol")
    login(client, auditor)
    record(AuditEvent(action=AuditAction.USER_UPDATED, user_id=auditor.id,
                      object_type="user", object_id="=HYPERLINK(\"http://x\")"))
    r = client.get("/api/v1/audit/export.csv", params={"user_id": auditor.id})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("\ufeff")
    assert "id;ts;username;action" in text
    assert "'=HYPERLINK" in text
    page = client.get("/api/v1/audit", params={"user_id": auditor.id, "action": "audit.exported"}).json()
    assert page["total"] >= 1


def test_verify_endpoint(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("admin"))
    r = client.post("/api/v1/audit/verify")
    assert r.status_code == 200
    assert r.json()["ok"] is True
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_audit_api.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implementatsiya**

`backend/app/audit/schemas.py`:
```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditOut(BaseModel):
    id: int
    ts: datetime
    user_id: int | None
    username: str | None
    action: str
    result: str
    object_type: str | None
    object_id: str | None
    request_id: str | None
    details: dict[str, Any]
    ip: str | None


class VerifyOut(BaseModel):
    ok: bool
    checked: int
    first_bad_id: int | None
```

`backend/app/audit/router.py`:
```python
"""Audit jurnalini ko'rish (faqat audit:read — administrator va ichki nazorat)."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin.schemas import Page
from app.audit.schemas import AuditOut, VerifyOut
from app.audit.service import AuditAction, ip_aad, log_event, verify_chain_snapshot
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core import keystore
from app.core.crypto import CryptoError, Purpose
from app.core.db import get_db
from app.core.request_meta import Meta

router = APIRouter(prefix="/audit", tags=["audit"])
DB = Annotated[Session, Depends(get_db)]
Auditor = Annotated[AuthContext, Depends(require_perm(Perm.AUDIT_READ))]
EXPORT_LIMIT = 50_000
DEFAULT_WINDOW = timedelta(days=30)
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class Filters:
    def __init__(
        self,
        from_ts: Annotated[datetime | None, Query()] = None,
        to_ts: Annotated[datetime | None, Query()] = None,
        user_id: Annotated[int | None, Query(gt=0)] = None,
        action: Annotated[str | None, Query(max_length=64, pattern=r"^[a-z_.]+$")] = None,
        result: Annotated[str | None, Query(pattern=r"^(ok|fail|denied)$")] = None,
    ) -> None:
        self.from_ts = from_ts or datetime.now(UTC) - DEFAULT_WINDOW
        self.to_ts = to_ts
        self.user_id = user_id
        self.action = action
        self.result = result

    def sql(self) -> tuple[str, dict[str, Any]]:
        clauses = ["a.ts >= :from_ts"]
        params: dict[str, Any] = {"from_ts": self.from_ts}
        if self.to_ts is not None:
            clauses.append("a.ts < :to_ts")
            params["to_ts"] = self.to_ts
        if self.user_id is not None:
            clauses.append("a.user_id = :user_id")
            params["user_id"] = self.user_id
        if self.action:
            clauses.append("a.action LIKE :action")
            params["action"] = self.action.replace("_", "\\_") + "%"
        if self.result:
            clauses.append("a.result = :result")
            params["result"] = self.result
        return " AND ".join(clauses), params

    def as_dict(self) -> dict[str, Any]:
        return {"from_ts": self.from_ts.isoformat(), "to_ts": self.to_ts.isoformat() if self.to_ts else None,
                "user_id": self.user_id, "action": self.action, "result": self.result}


_SELECT = (
    "SELECT a.id, a.ts, a.user_id, u.username, a.action, a.result, a.object_type, a.object_id, "
    "a.request_id, a.details, a.ip_enc FROM core.audit_log a "
    "LEFT JOIN core.users u ON u.id = a.user_id WHERE {where} ORDER BY a.id DESC LIMIT :limit OFFSET :offset"
)


def _ip(audit_id: int, blob: bytes | None) -> str | None:
    if blob is None:
        return None
    try:
        return keystore.decrypt_str(Purpose.AUDIT, blob, ip_aad(audit_id))
    except CryptoError:
        return None


def _rows(db: Session, filters: Filters, limit: int, offset: int) -> list[AuditOut]:
    where, params = filters.sql()
    result = db.execute(text(_SELECT.format(where=where)), {**params, "limit": limit, "offset": offset})
    return [
        AuditOut(
            id=r["id"], ts=r["ts"], user_id=r["user_id"], username=r["username"], action=r["action"],
            result=r["result"], object_type=r["object_type"], object_id=r["object_id"],
            request_id=r["request_id"], details=r["details"], ip=_ip(r["id"], r["ip_enc"]),
        )
        for r in result.mappings()
    ]


@router.get("")
def list_audit(
    ctx: Auditor,
    db: DB,
    filters: Annotated[Filters, Depends()],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Page[AuditOut]:
    where, params = filters.sql()
    total = db.execute(text(f"SELECT count(*) FROM core.audit_log a WHERE {where}"), params).scalar_one()
    items = _rows(db, filters, page_size, (page - 1) * page_size)
    return Page[AuditOut](items=items, total=int(total), page=page, page_size=page_size)


def _cell(value: object) -> str:
    text_value = "" if value is None else str(value)
    return "'" + text_value if text_value.startswith(_FORMULA_PREFIXES) else text_value


@router.get("/export.csv")
def export_csv(ctx: Auditor, db: DB, meta: Meta, filters: Annotated[Filters, Depends()]) -> Response:
    rows = _rows(db, filters, EXPORT_LIMIT, 0)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(["id", "ts", "username", "action", "result", "object_type", "object_id",
                     "request_id", "ip", "details"])
    for r in rows:
        writer.writerow([_cell(v) for v in (
            r.id, r.ts.isoformat(), r.username, r.action, r.result, r.object_type, r.object_id,
            r.request_id, r.ip, json.dumps(r.details, ensure_ascii=False))])
    log_event(meta, AuditAction.AUDIT_EXPORTED, user_id=ctx.user_id,
              details={"filters": filters.as_dict(), "rows": len(rows)})
    filename = f"audit_{datetime.now(UTC):%Y%m%d_%H%M}.csv"
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/verify")
def verify(ctx: Auditor, meta: Meta) -> VerifyOut:
    report = verify_chain_snapshot()
    log_event(meta, AuditAction.AUDIT_VERIFIED, user_id=ctx.user_id,
              result="ok" if report.ok else "fail",
              details={"checked": report.checked, "first_bad_id": report.first_bad_id})
    return VerifyOut(ok=report.ok, checked=report.checked, first_bad_id=report.first_bad_id)
```

`backend/app/main.py` — import va `include_router`:
```python
from app.audit.router import router as audit_router
```
```python
    app.include_router(audit_router, prefix=API_PREFIX)
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed (jumladan `test_route_guards` audit route'larini ham tekshiradi).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(audit): audit ro'yxati, xavfsiz CSV eksport, zanjirni tekshirish API"
```

---

### Task 13: Kalit rotatsiyasi, CLI, OpenAPI, dev stack (Caddy) va hujjat

**Files:**
- Create: `backend/app/core/reencrypt.py`, `backend/app/admin/keys_router.py`, `backend/app/cli.py`, `deploy/compose.yml`, `deploy/caddy/Caddyfile.dev`, `deploy/secrets.example/README.md`, `Makefile`, `README.md`
- Modify: `backend/app/main.py` (keys router, openapi)
- Test: `backend/tests/test_keys_cli.py`

**Interfaces:**
- Consumes: `keystore.rotate/load_keyring/invalidate_keyring/rewrap_all`, `blob_version`, `Purpose`, `require_perm(Perm.ADMIN_KEYS)`, `verify_chain_snapshot`, `passwords`, `Position`, `User`.
- Produces: `app.core.reencrypt`: `EncryptedColumn(table, pk, column, purpose)` + `.aad(pk)`, `REGISTRY`, `NON_RETIRABLE = {Purpose.AUDIT}`, `reencrypt(conn, ring, purpose, batch=500) -> int`, `versions_in_use(conn, purpose) -> set[int]`, `retire_unused(conn, purpose, grace) -> list[int]`. HTTP `GET /admin/keys` → `list[KeyOut]`, `POST /admin/keys/{purpose}/rotate` → `RotateOut(purpose, version, reencrypted)`; `GET /openapi.json` (dev — ochiq, prod — `admin:settings`). CLI: `python -m app.cli {create-admin,rotate-key,retire-keys,rewrap-keys,audit-verify,cleanup}`; `app.cli.main(argv) -> int`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_keys_cli.py`:
```python
import base64
import os
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import cli
from app.auth.models import User
from app.core import keystore
from app.core.crypto import Purpose, blob_version
from app.core.db import get_engine, new_session
from app.core.reencrypt import retire_unused, versions_in_use
from app.main import create_app
from tests.helpers import SeedUser, login


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


def test_rotate_mfa_reencrypts_and_login_still_works(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    other = make_user("rukovodstvo")
    login(client, make_user("admin"))
    r = client.post("/api/v1/admin/keys/mfa/rotate")
    assert r.status_code == 200, r.text
    version = r.json()["version"]
    assert r.json()["reencrypted"] >= 2
    with new_session() as s:
        blob = s.execute(select(User.totp_secret_enc).where(User.id == other.id)).scalar_one()
    assert blob is not None and blob_version(blob) == version
    login(TestClient(client.app, base_url="https://testserver"), other)
    keys = client.get("/api/v1/admin/keys").json()
    mfa = [k for k in keys if k["purpose"] == "mfa"]
    assert {k["status"] for k in mfa} >= {"active", "decrypt_only"}


def test_retire_unused_respects_grace() -> None:
    with get_engine("app").begin() as conn:
        assert retire_unused(conn, Purpose.MFA, grace=timedelta(hours=1)) == []
        in_use = versions_in_use(conn, Purpose.MFA)
        retired = retire_unused(conn, Purpose.MFA, grace=timedelta(0))
        assert not set(retired) & in_use
        wrapped = conn.execute(
            text("SELECT wrapped_key FROM core.crypto_keys WHERE purpose='mfa' AND status='retired'")
        ).scalars().all()
    assert all(bytes(w) == b"" for w in wrapped)
    keystore.invalidate_keyring()


def test_rotate_unknown_purpose_is_422(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("admin"))
    assert client.post("/api/v1/admin/keys/nope/rotate").status_code == 422


def test_non_admin_cannot_rotate(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("vnutr_kontrol"))
    assert client.post("/api/v1/admin/keys/mfa/rotate").status_code == 403


def test_openapi_available_in_dev(client: TestClient) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/auth/login" in spec["paths"]


def test_cli_create_admin_and_audit_verify(capsys: pytest.CaptureFixture[str]) -> None:
    username = f"cli.{os.urandom(3).hex()}"
    assert cli.main(["create-admin", "--username", username, "--full-name", "Администратор"]) == 0
    out = capsys.readouterr().out
    assert username in out and "Vaqtinchalik parol:" in out
    assert cli.main(["create-admin", "--username", username, "--full-name", "X"]) == 1
    assert cli.main(["audit-verify"]) == 0
    assert cli.main(["cleanup"]) == 0


def test_cli_rewrap_roundtrip(tmp_path: Path) -> None:
    from app.core.config import get_settings

    new_kek = os.urandom(32)
    path = tmp_path / "kek"
    path.write_text(base64.b64encode(new_kek).decode())
    assert cli.main(["rewrap-keys", "--new-kek-file", str(path)]) == 0
    with get_engine("app").begin() as conn:
        keystore.rewrap_all(conn, new_kek, get_settings().key_bytes("master_kek"))
    keystore.invalidate_keyring()
    assert keystore.decrypt(Purpose.PII, keystore.encrypt(Purpose.PII, b"x", "a"), "a") == b"x"
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_keys_cli.py -v`
Expected: FAIL — `ImportError: cannot import name 'cli'`.

- [ ] **Step 3: Implementatsiya — qayta shifrlash**

`backend/app/core/reencrypt.py`:
```python
"""Shifrlangan ustunlar reyestri va kalit rotatsiyasidan keyin qayta shifrlash.

Audit (AUDIT maqsadi) qayta shifrlanmaydi: jurnal faqat qo'shishga ochiq va hash-chain
shifrmatnni o'z ichiga oladi. Eski AUDIT kalitlari 1 yillik saqlash muddati davomida
`decrypt_only` holatida qoladi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.crypto import Keyring, Purpose


@dataclass(frozen=True, slots=True)
class EncryptedColumn:
    table: str
    pk: str
    column: str
    purpose: Purpose

    def aad(self, pk_value: object) -> str:
        return f"{self.table}.{self.column}:{pk_value}"


REGISTRY: tuple[EncryptedColumn, ...] = (
    EncryptedColumn("core.users", "id", "totp_secret_enc", Purpose.MFA),
    EncryptedColumn("core.sessions", "id", "ip_enc", Purpose.PII),
)
NON_RETIRABLE = frozenset({Purpose.AUDIT})
_VERSION_SQL = "(get_byte({col}, 1) * 256 + get_byte({col}, 2))"


def _columns(purpose: Purpose) -> list[EncryptedColumn]:
    return [c for c in REGISTRY if c.purpose == purpose]


def reencrypt(conn: Connection, ring: Keyring, purpose: Purpose, batch: int = 500) -> int:
    active = ring.active[purpose]
    total = 0
    for col in _columns(purpose):
        version = _VERSION_SQL.format(col=col.column)
        # Identifikatorlar faqat REGISTRY'dan olinadi — foydalanuvchi kiritmaydi.
        select_sql = text(
            f"SELECT {col.pk}, {col.column} FROM {col.table} "  # noqa: S608
            f"WHERE {col.column} IS NOT NULL AND {version} <> :v LIMIT :n FOR UPDATE"
        )
        update_sql = text(f"UPDATE {col.table} SET {col.column} = :b WHERE {col.pk} = :pk")  # noqa: S608
        while True:
            rows = conn.execute(select_sql, {"v": active, "n": batch}).all()
            if not rows:
                break
            for pk, blob in rows:
                plain = ring.decrypt(purpose, bytes(blob), col.aad(pk))
                conn.execute(update_sql, {"b": ring.encrypt(purpose, plain, col.aad(pk)), "pk": pk})
            total += len(rows)
    return total


def versions_in_use(conn: Connection, purpose: Purpose) -> set[int]:
    used: set[int] = set()
    for col in _columns(purpose):
        version = _VERSION_SQL.format(col=col.column)
        used |= set(
            conn.execute(
                text(f"SELECT DISTINCT {version} FROM {col.table} WHERE {col.column} IS NOT NULL")  # noqa: S608
            ).scalars()
        )
    return used


def retire_unused(conn: Connection, purpose: Purpose, grace: timedelta) -> list[int]:
    """Ishlatilmayotgan `decrypt_only` versiyalarni yo'q qiladi (o'ralgan kalit o'chiriladi).

    Faol versiya `grace` dan eski bo'lishi shart: boshqa worker'larning keyring keshi
    (60 s) eski versiya bilan yozib ulgurgan qiymatlar qolmasligi uchun.
    """
    if purpose in NON_RETIRABLE:
        return []
    fresh = conn.execute(
        text(
            "SELECT 1 FROM core.crypto_keys WHERE purpose = :p AND status = 'active' "
            "AND created_at > now() - :g"
        ),
        {"p": purpose.value, "g": grace},
    ).first()
    if fresh is not None:
        return []
    in_use = sorted(versions_in_use(conn, purpose))
    return list(
        conn.execute(
            text(
                "UPDATE core.crypto_keys SET status = 'retired', retired_at = now(), "
                "wrapped_key = '\\x'::bytea "
                "WHERE purpose = :p AND status = 'decrypt_only' AND NOT (version = ANY(:used)) "
                "RETURNING version"
            ),
            {"p": purpose.value, "used": in_use},
        ).scalars()
    )
```

- [ ] **Step 4: Implementatsiya — kalitlar API**

`backend/app/admin/keys_router.py`:
```python
"""Shifrlash kalitlari holati va rotatsiyasi (admin:keys)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, log_event
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose
from app.core.db import get_db
from app.core.reencrypt import reencrypt
from app.core.request_meta import Meta

router = APIRouter(prefix="/admin/keys", tags=["admin"])
DB = Annotated[Session, Depends(get_db)]
KeysAdmin = Annotated[AuthContext, Depends(require_perm(Perm.ADMIN_KEYS))]


class KeyOut(BaseModel):
    purpose: str
    version: int
    status: str
    created_at: datetime
    retired_at: datetime | None


class RotateOut(BaseModel):
    purpose: str
    version: int
    reencrypted: int


@router.get("")
def list_keys(ctx: KeysAdmin, db: DB) -> list[KeyOut]:
    rows = db.execute(
        text(
            "SELECT purpose, version, status, created_at, retired_at FROM core.crypto_keys "
            "ORDER BY purpose, version"
        )
    ).mappings()
    return [KeyOut(**row) for row in rows]


@router.post("/{purpose}/rotate")
def rotate_key(purpose: Purpose, ctx: KeysAdmin, db: DB, meta: Meta) -> RotateOut:
    kek = get_settings().key_bytes("master_kek")
    conn = db.connection()
    version = keystore.rotate(conn, kek, purpose)
    count = reencrypt(conn, keystore.load_keyring(conn, kek), purpose)
    keystore.invalidate_keyring()
    log_event(meta, AuditAction.KEY_ROTATED, user_id=ctx.user_id, object_type="key",
              object_id=purpose.value, details={"version": version, "reencrypted": count})
    return RotateOut(purpose=purpose.value, version=version, reencrypted=count)
```

`backend/app/main.py` — import'lar va `create_app` oxiriga qo'shing:
```python
from typing import Any

from fastapi import Depends

from app.admin.keys_router import router as keys_router
from app.auth.context import require_perm
from app.auth.permissions import Perm
```
`app.include_router(audit_router, ...)` dan keyin:
```python
    app.include_router(keys_router, prefix=API_PREFIX)
    _mount_openapi(app, protected=settings.env == "prod")
```
va modul darajasida:
```python
def _mount_openapi(app: FastAPI, *, protected: bool) -> None:
    dependencies = [Depends(require_perm(Perm.ADMIN_SETTINGS))] if protected else []

    @app.get(f"{API_PREFIX}/openapi.json", include_in_schema=False, dependencies=dependencies)
    def openapi() -> dict[str, Any]:
        return app.openapi()
```

- [ ] **Step 5: Implementatsiya — CLI**

`backend/app/cli.py`:
```python
"""Operator buyruqlari: python -m app.cli <buyruq>.

create-admin   — birinchi administrator (vaqtinchalik parol bir marta chiqariladi)
rotate-key     — DEK rotatsiyasi + qayta shifrlash
retire-keys    — ishlatilmayotgan eski DEK'larni yo'q qilish
rewrap-keys    — KEK rotatsiyasi (keyin master_kek sirini almashtirib, qayta ishga tushiring)
audit-verify   — audit zanjirini tekshirish (buzilgan bo'lsa chiqish kodi 2)
cleanup        — eskirgan sessiya va 2FA challenge'larni o'chirish
"""

from __future__ import annotations

import argparse
import base64
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, or_, select

from app.audit.service import verify_chain_snapshot
from app.auth import passwords
from app.auth.models import MfaChallenge, Position, User, UserSession
from app.auth.permissions import ADMIN_ROLE
from app.auth.service import normalize_username
from app.bootstrap import bootstrap_runtime
from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session
from app.core.reencrypt import reencrypt, retire_unused


def _out(message: str) -> None:
    sys.stdout.write(message + "\n")


def _create_admin(username: str, full_name: str) -> int:
    uname = normalize_username(username)
    with new_session() as db:
        if db.execute(select(User.id).where(User.username == uname)).first() is not None:
            _out(f"Xato: '{uname}' allaqachon mavjud")
            return 1
        position_id = db.execute(select(Position.id).where(Position.code == ADMIN_ROLE)).scalar_one()
        temporary = passwords.generate_temporary_password()
        db.add(User(username=uname, full_name=full_name, position_id=position_id,
                    password_hash=passwords.hash_password(temporary),
                    password_changed_at=datetime.now(UTC), must_change_password=True))
        db.commit()
    _out(f"Administrator yaratildi: {uname}")
    _out(f"Vaqtinchalik parol: {temporary}")
    _out("Birinchi kirishda 2FA ulanadi va parol almashtiriladi.")
    return 0


def _rotate(purpose: Purpose) -> int:
    kek = get_settings().key_bytes("master_kek")
    with get_engine("app").begin() as conn:
        version = keystore.rotate(conn, kek, purpose)
        count = reencrypt(conn, keystore.load_keyring(conn, kek), purpose)
    keystore.invalidate_keyring()
    _out(f"{purpose.value}: yangi versiya {version}, qayta shifrlandi: {count}")
    return 0


def _retire(grace_minutes: int) -> int:
    with get_engine("app").begin() as conn:
        for purpose in Purpose:
            retired = retire_unused(conn, purpose, timedelta(minutes=grace_minutes))
            if retired:
                _out(f"{purpose.value}: yo'q qilindi {retired}")
    return 0


def _rewrap(new_kek_file: Path) -> int:
    new_kek = base64.b64decode(new_kek_file.read_text().strip(), validate=True)
    if len(new_kek) != 32:
        _out("Xato: yangi KEK 32 bayt bo'lishi kerak")
        return 1
    with get_engine("app").begin() as conn:
        count = keystore.rewrap_all(conn, get_settings().key_bytes("master_kek"), new_kek)
    _out(f"{count} ta kalit qayta o'raldi. Endi master_kek sirini almashtirib, servislarni qayta ishga tushiring.")
    return 0


def _audit_verify() -> int:
    report = verify_chain_snapshot()
    _out(f"ok={report.ok} checked={report.checked} first_bad_id={report.first_bad_id}")
    return 0 if report.ok else 2


def _cleanup() -> int:
    now = datetime.now(UTC)
    with new_session() as db:
        challenges = db.execute(
            delete(MfaChallenge).where(MfaChallenge.expires_at < now - timedelta(days=1))
        ).rowcount  # type: ignore[attr-defined]
        old = now - timedelta(days=30)
        stale = db.execute(
            delete(UserSession).where(
                or_(UserSession.absolute_expires_at < old, UserSession.revoked_at < old)
            )
        ).rowcount  # type: ignore[attr-defined]
        db.commit()
    _out(f"o'chirildi: challenge={challenges}, sessiya={stale}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--username", required=True)
    p.add_argument("--full-name", required=True)
    p = sub.add_parser("rotate-key")
    p.add_argument("--purpose", required=True, choices=[x.value for x in Purpose])
    p = sub.add_parser("retire-keys")
    p.add_argument("--grace-minutes", type=int, default=10)
    p = sub.add_parser("rewrap-keys")
    p.add_argument("--new-kek-file", type=Path, required=True)
    sub.add_parser("audit-verify")
    sub.add_parser("cleanup")
    args = parser.parse_args(argv)

    bootstrap_runtime()
    if args.command == "create-admin":
        return _create_admin(args.username, args.full_name)
    if args.command == "rotate-key":
        return _rotate(Purpose(args.purpose))
    if args.command == "retire-keys":
        return _retire(args.grace_minutes)
    if args.command == "rewrap-keys":
        return _rewrap(args.new_kek_file)
    if args.command == "audit-verify":
        return _audit_verify()
    return _cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest -v`
Expected: barcha testlar passed.

- [ ] **Step 7: Dev stack (Caddy + secrets) va hujjatlar**

`deploy/caddy/Caddyfile.dev`:
```
{
	admin off
}

localhost {
	tls internal
	encode zstd gzip

	request_body {
		max_size 1MB
	}

	header {
		Strict-Transport-Security "max-age=63072000; includeSubDomains"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
		Referrer-Policy "no-referrer"
		Permissions-Policy "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
		Cross-Origin-Opener-Policy "same-origin"
		Cross-Origin-Resource-Policy "same-origin"
		Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
		-Server
	}

	# Probe'lar faqat ichki tarmoq uchun.
	@probes path /api/v1/healthz /api/v1/readyz
	respond @probes 404

	handle /api/* {
		reverse_proxy api:8000
	}

	handle {
		respond "UGEKAZNA API ishlayapti. Frontend 3-rejada qo'shiladi." 200
	}
}
```

`deploy/compose.yml`:
```yaml
# Dev stack. Faqat caddy tashqi port ochadi (https://localhost:8443).
# Sirlar: python scripts/gen_secrets.py  →  deploy/secrets/
name: ugekazna

x-hardening: &hardening
  restart: unless-stopped
  read_only: true
  cap_drop: [ALL]
  security_opt: ["no-new-privileges:true"]
  logging:
    driver: json-file
    options: {max-size: "10m", max-file: "3"}

secrets:
  db_superuser_password: {file: ./secrets/db_superuser_password}
  db_migrator_password: {file: ./secrets/db_migrator_password}
  db_app_password: {file: ./secrets/db_app_password}
  db_etl_password: {file: ./secrets/db_etl_password}
  redis_password: {file: ./secrets/redis_password}
  master_kek: {file: ./secrets/master_kek}
  blind_index_key: {file: ./secrets/blind_index_key}
  session_pepper: {file: ./secrets/session_pepper}

services:
  db:
    <<: *hardening
    image: postgres:16-alpine
    user: "70:70"
    group_add: ["10001"]
    environment:
      POSTGRES_USER: postgres
      POSTGRES_DB: ugekazna
      POSTGRES_PASSWORD_FILE: /run/secrets/db_superuser_password
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C.UTF-8"
    secrets: [db_superuser_password, db_migrator_password, db_app_password, db_etl_password]
    volumes:
      - db_data:/var/lib/postgresql/data
      - ./postgres/initdb:/docker-entrypoint-initdb.d:ro
    tmpfs:
      - /tmp
      - /var/run/postgresql:uid=70,gid=70,mode=0775
    networks: [backend]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U postgres -d ugekazna"]
      interval: 5s
      timeout: 3s
      retries: 30

  redis:
    <<: *hardening
    image: redis:7-alpine
    user: "999:1000"
    group_add: ["10001"]
    secrets: [redis_password]
    tmpfs: ["/tmp:mode=1777"]
    command:
      - sh
      - -c
      - >-
        umask 077 &&
        printf 'requirepass %s\n' "$$(cat /run/secrets/redis_password)" > /tmp/redis.conf &&
        exec redis-server /tmp/redis.conf --save '' --appendonly no
        --maxmemory 256mb --maxmemory-policy allkeys-lru
    networks: [backend]
    healthcheck:
      test: ["CMD-SHELL", "redis-cli --no-auth-warning -a \"$$(cat /run/secrets/redis_password)\" ping | grep -q PONG"]
      interval: 5s
      timeout: 3s
      retries: 30

  migrate:
    <<: *hardening
    restart: "no"
    build: {context: ../backend, args: {INSTALL_DEV: "true"}}
    image: ugekazna-backend:dev
    user: "10001:10001"
    environment: {ENV: dev}
    secrets: [db_migrator_password, db_app_password, master_kek, blind_index_key, session_pepper]
    command: ["alembic", "upgrade", "head"]
    tmpfs: [/tmp]
    networks: [backend]
    depends_on:
      db: {condition: service_healthy}

  api:
    <<: *hardening
    image: ugekazna-backend:dev
    user: "10001:10001"
    environment:
      ENV: dev
      BASE_URL: https://localhost:8443
      WATCHFILES_FORCE_POLLING: "true"
    secrets: [db_app_password, redis_password, master_kek, blind_index_key, session_pepper]
    volumes:
      - ../backend/app:/app/app:ro
    tmpfs: [/tmp]
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload",
              "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header", "--no-access-log"]
    networks: [backend, edge]
    depends_on:
      migrate: {condition: service_completed_successfully}
      redis: {condition: service_healthy}

  caddy:
    <<: *hardening
    image: caddy:2-alpine
    cap_add: [NET_BIND_SERVICE]
    ports: ["8443:443"]
    volumes:
      - ./caddy/Caddyfile.dev:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks: [edge]
    depends_on: [api]

networks:
  backend:
    internal: true
  edge: {}

volumes:
  db_data:
  caddy_data:
  caddy_config:
```

`deploy/secrets.example/README.md`:
```markdown
# Sirlar

Haqiqiy fayllar `deploy/secrets/` da (git'ga tushmaydi). Yaratish: `python scripts/gen_secrets.py`.

| Fayl | Mazmun |
|---|---|
| db_superuser_password | PostgreSQL superuser (faqat initdb) |
| db_migrator_password | ugk_migrator — faqat migratsiyalar |
| db_app_password | ugk_app — API |
| db_etl_password | ugk_etl — ETL worker |
| redis_password | Redis `requirepass` |
| master_kek | base64, 32 bayt — DEK'larni o'raydi |
| blind_index_key | base64, 32 bayt — shifrlangan maydon qidiruvi |
| session_pepper | base64, 32 bayt — token HMAC'lari |

Prod (Linux): `chown root:10001 deploy/secrets/* && chmod 0440 deploy/secrets/*`.
`master_kek` zaxirasi boshqa joyda (seyf/HSM) saqlanadi — u yo'qolsa shifrlangan ma'lumot tiklanmaydi.
```

`Makefile`:
```makefile
# Linux/prod uchun. Windows'da README'dagi buyruqlarni to'g'ridan-to'g'ri ishlating.
COMPOSE := docker compose -f deploy/compose.yml
TEST    := docker compose -f deploy/compose.test.yml run --rm test

.PHONY: secrets lock build up down logs create-admin test lint typecheck

secrets: ## Sirlarni yaratish (mavjudlariga tegmaydi)
	python3 scripts/gen_secrets.py

lock: ## requirements*.txt ni hash bilan qulflash
	docker run --rm -v "$(CURDIR)/backend:/w" -w /w python:3.12-slim-bookworm sh -c \
	  "pip install -q 'pip-tools>=7.5' && \
	   pip-compile -q --strip-extras --generate-hashes --allow-unsafe -o requirements.txt requirements.in && \
	   pip-compile -q --strip-extras --generate-hashes --allow-unsafe -o requirements-dev.txt requirements-dev.in"

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

create-admin: ## make create-admin u=admin n="Администратор"
	$(COMPOSE) exec api python -m app.cli create-admin --username "$(u)" --full-name "$(n)"

test:
	$(TEST) pytest

lint:
	$(TEST) ruff check app tests

typecheck:
	$(TEST) mypy app
```

`README.md` (repo ildizi):
```markdown
# UGEKAZNA

«Узбекгидроэнерго» AJ uchun UGE ERP ustidagi analitik BI-qatlam.
Spec: `docs/superpowers/specs/`, rejalar: `docs/superpowers/plans/`, TZ: `docs/reference/UGEKAZNA_TZ.pdf`.

## Tez boshlash (dev, Windows / Git Bash)

```bash
python scripts/gen_secrets.py
docker compose -f deploy/compose.yml up -d --build
docker compose -f deploy/compose.yml exec api python -m app.cli create-admin --username admin --full-name "Администратор"
```
API: https://localhost:8443/api/v1/ (sertifikat Caddy'ning ichki CA'si — brauzer ogohlantiradi).

## Testlar

```bash
docker compose -f deploy/compose.test.yml run --rm test pytest
docker compose -f deploy/compose.test.yml run --rm test ruff check app tests
docker compose -f deploy/compose.test.yml run --rm test mypy app
docker compose -f deploy/compose.test.yml down
```

## Xavfsizlik asoslari

- Sirlar faqat Docker secrets orqali (`deploy/secrets.example/README.md`).
- Parollar Argon2id; hamma uchun majburiy TOTP 2FA.
- Sezgir ustunlar AES-256-GCM (envelope, KEK → DEK), kalit rotatsiyasi: `python -m app.cli rotate-key --purpose mfa`.
- Audit jurnali faqat qo'shishga ochiq, hash-chain: `python -m app.cli audit-verify`.
```

- [ ] **Step 8: Dev stack smoke-test**

```bash
python scripts/gen_secrets.py
docker compose -f deploy/compose.yml up -d --build
docker compose -f deploy/compose.yml ps
curl -sk https://localhost:8443/api/v1/healthz
curl -sk -X POST https://localhost:8443/api/v1/auth/login -H 'Content-Type: application/json' -d '{"username":"nobody","password":"x"}'
curl -skI https://localhost:8443/api/v1/auth/me | grep -iE "content-security|strict-transport|x-request-id"
docker compose -f deploy/compose.yml exec api python -m app.cli create-admin --username admin --full-name "Администратор"
```
Expected: `ps` — `db`, `redis`, `api`, `caddy` healthy/running, `migrate` exited (0); `healthz` → HTTP 404 (Caddy tashqaridan yopadi); login → `{"error":{"code":"invalid_credentials",...}}`; `/auth/me` sarlavhalarida CSP, HSTS va `X-Request-ID` bor; create-admin vaqtinchalik parolni chiqaradi.

Agar `db` yoki `redis` konteyneri `read_only`/`user` sababli ishga tushmasa: `docker compose -f deploy/compose.yml logs db redis` ni ko'rib, sababni aniqlang (masalan, tmpfs egasi) va tuzating — hardening'ni olib tashlamang.

- [ ] **Step 9: Lint va tiplar**

Run: `$TEST ruff check app tests && $TEST mypy app`
Expected: `All checks passed!` va `Success: no issues found`. Topilgan muammolarni tuzating va `$TEST pytest` ni qayta ishga tushiring.

- [ ] **Step 10: Spec'ga chetlanishlarni yozish va commit**

`docs/superpowers/specs/2026-09-24-poydevor-design.md` — 6.3 bo'limidagi "SQLAlchemy 2.0 async" ni "SQLAlchemy 2.0 (sinxron, threadpool)" ga, 3.1 bo'limidagi "10 ta zaxira kod — Argon2id xeshi" ni "10 ta zaxira kod — HMAC-SHA256(session_pepper), bir martalik" ga almashtiring.

```bash
git add backend deploy scripts Makefile README.md docs
git commit -m "feat: kalit rotatsiyasi, operator CLI, OpenAPI, dev stack (Caddy) va hujjat"
```
