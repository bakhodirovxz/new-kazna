# UGEKAZNA — Linux/CI buyruqlari (`make help`). Windows: scripts/dev.ps1 <target> — xuddi shu nomlar.
# STACK=dev (standart: deploy/compose.yml) yoki STACK=prod (deploy/compose.prod.yml + deploy/prod.env
# + deploy/release.env) — operator buyruqlari (create-admin, audit-verify, rotate-keys, …) uchun.
SHELL   := /bin/bash
STACK   ?= dev
VERSION ?= $(shell git describe --tags --always --dirty)

DEV  := docker compose -f deploy/compose.yml
PROD := docker compose -f deploy/compose.prod.yml --env-file deploy/prod.env --env-file deploy/release.env
TEST := docker compose -f deploy/compose.test.yml run --rm test
NODE := docker compose -f deploy/compose.frontend.yml run --rm node

ifeq ($(STACK),prod)
  STACK_COMPOSE := $(PROD)
else ifeq ($(STACK),dev)
  STACK_COMPOSE := $(DEV)
else
  $(error STACK faqat dev yoki prod bo'lishi mumkin)
endif
CLI := $(STACK_COMPOSE) run --rm -T migrate python -m app.cli

.DEFAULT_GOAL := help

.PHONY: help
help: ## buyruqlar ro'yxati
	@grep -hE '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

# ── Dev stack ────────────────────────────────────────────────────────────────
.PHONY: secrets lock build up down logs web
secrets: ## sirlarni yaratish (mavjudlariga tegmaydi)
	python3 scripts/gen_secrets.py
lock: ## requirements*.txt ni hash bilan qulflash (pip-compile --generate-hashes)
	docker run --rm -v "$(CURDIR)/backend:/w" -w /w python:3.12-slim-bookworm sh -c \
	  "pip install -q 'pip-tools>=7.5' && \
	   pip-compile -q --strip-extras --generate-hashes --allow-unsafe -o requirements.txt requirements.in && \
	   pip-compile -q --strip-extras --generate-hashes --allow-unsafe -o requirements-dev.txt requirements-dev.in"
build: ## dev image'larini qurish
	$(DEV) build
up: ## dev stack'ni ishga tushirish (https://localhost:8443)
	$(DEV) up -d
down: ## dev stack'ni to'xtatish
	$(DEV) down
logs: ## dev loglari
	$(DEV) logs -f --tail=100
web: ## frontend'ni qayta qurish va Caddy'ni yangilash
	$(DEV) up -d --build caddy

# ── Operator buyruqlari (STACK=dev|prod) ────────────────────────────────────
.PHONY: migrate create-admin seed-synthetic etl-run rollback-build audit-verify rotate-keys retire-keys rewrap-keys ops-check
migrate: ## alembic upgrade head (migrate servisi)
	$(STACK_COMPOSE) run --rm -T migrate
create-admin: ## make create-admin u=admin n="Администратор" [STACK=prod]
	$(STACK_COMPOSE) exec -T api python -m app.cli create-admin --username "$(u)" --full-name "$(n)"
seed-synthetic: ## dev: sintetik ma'lumotni to'liq yuklash
	$(DEV) exec -T worker python -m app.cli etl-run --source synthetic --mode full
MODE ?= incremental

etl-run: ## make etl-run SOURCE=file MODE=incremental [STACK=prod]
	$(STACK_COMPOSE) exec -T worker python -m app.cli etl-run --source "$(SOURCE)" --mode "$(MODE)"
rollback-build: ## aktiv build'ni qaytarish: make rollback-build [BUILD=id] [STACK=prod]
	$(STACK_COMPOSE) exec -T worker python -m app.cli rollback-build $(if $(BUILD),--build $(BUILD),)
audit-verify: ## audit HMAC-zanjirini tekshirish (buzilgan bo'lsa kod 2) [STACK=prod]
	$(CLI) audit-verify
rotate-keys: ## DEK rotatsiyasi + qayta shifrlash: make rotate-keys PURPOSE=pii [STACK=prod]
	$(CLI) rotate-key --purpose "$(PURPOSE)"
retire-keys: ## ishlatilmayotgan eski DEK'larni yo'q qilish (ugk_migrator) [STACK=prod]
	$(CLI) retire-keys
rewrap-keys: ## KEK rotatsiyasi: make rewrap-keys f=/abs/path/new_kek [STACK=prod] (key-management.md)
	$(STACK_COMPOSE) run --rm -T -v "$(f):/tmp/new_kek:ro" migrate python -m app.cli rewrap-keys --new-kek-file /tmp/new_kek
ops-check: ## ekspluatatsiya tekshiruvi worker ichida [STACK=prod]
	$(STACK_COMPOSE) exec -T worker python -m app.cli ops-check

# ── Sifat darvozalari (spec 10) ────────────────────────────────────────────────
.PHONY: test lint typecheck check check-backend check-frontend check-repo hooks fe-install fe-check e2e e2e-ci
test: ## backend testlari (pytest)
	$(TEST) pytest
lint: ## ruff
	$(TEST) ruff check app tests tools
typecheck: ## mypy --strict
	$(TEST) mypy app tools
check: ## barcha darvozalar: repo + backend + frontend
	scripts/check.sh
check-backend: ## ruff + mypy + bandit + pip-audit + pytest (qamrov 85%/95%)
	scripts/check_backend.sh
check-frontend: ## tsc + eslint + vitest + npm audit
	scripts/check_frontend.sh
check-repo: ## gitleaks (butun tarix) + semgrep + hadolint
	scripts/check_repo.sh
hooks: ## pre-commit hook'ni ulash
	git config core.hooksPath .githooks
fe-install: ## frontend bog'liqliklari (package-lock.json bo'yicha)
	$(NODE) npm ci
fe-check: ## tsc + eslint + vitest
	$(NODE) npm run check
e2e: ## Playwright E2E (dev stack ishlab turishi kerak)
	./scripts/e2e.sh
e2e-ci: ## CI: toza dev stack + Playwright E2E (faqat bir martalik checkout; dev'da make e2e)
	scripts/e2e_ci.sh

# ── Ta'minot zanjiri va reliz ─────────────────────────────────────────────────
.PHONY: pin-images scan release
pin-images: ## base image'larni joriy digest'ga qotirish (deploy/images.lock.env)
	scripts/pin_images.sh
scan: ## prod image'lar + Trivy (HIGH/CRITICAL) + CycloneDX SBOM [VERSION=…]
	scripts/scan.sh $(VERSION)
release: ## reliz paketi: make release VERSION=1.0.0
	scripts/release.sh $(VERSION)

# ── Deploy testlari ──────────────────────────────────────────────────────────
.PHONY: prod-config test-caddy db-smoke backup-selftest load-test
prod-config: ## compose.prod.yml sintaksisi (docker compose config)
	scripts/prod_config.sh
test-caddy: ## Caddyfile.prod xatti-harakati (probe'lar, TLS, sarlavhalar, 1 MB, SPA)
	scripts/tests/caddy_prod_test.sh
db-smoke: ## DB image smoke-testi (profil, kengaytmalar, rollar, pgBackRest)
	scripts/tests/db_image_smoke.sh
backup-selftest: ## zaxira/tiklash avtotesti Docker'da (sekin, 10–25 daqiqa)
	scripts/backup_selftest.sh
load-test: ## k6 yuklama testi: dev stack + sintetik ma'lumot (UGK_LOAD_DURATION=20s — tez)
	scripts/load_test.sh

# ── Prod (Linux host, reliz papkasi) ─────────────────────────────────────────
.PHONY: prod-up prod-down prod-ps backup backup-status restore-test monitor
prod-up: ## prod: ishga tushirish/yangilash (migrate avtomatik)
	$(PROD) up -d
prod-down: ## prod: to'xtatish (volume'lar saqlanadi)
	$(PROD) down
prod-ps: ## prod: servislar holati
	$(PROD) ps
backup: ## prod: bir martalik zaxira — make backup [TYPE=full|diff]
	$(PROD) exec -T backup ugk-backup once $(or $(TYPE),full)
backup-status: ## prod: pgBackRest info va oxirgi tiklash testi
	$(PROD) exec -T backup ugk-backup info
	$(PROD) run --rm -T --no-deps migrate python -m app.cli restore-test-status
restore-test: ## prod: tiklash testi (vaqtinchalik klaster, natija core.settings'ga)
	scripts/restore_test.sh
monitor: ## prod: servislar holati + ops-check (systemd timer bilan bir xil)
	scripts/ops/monitor.sh
