# Linux/prod uchun. Windows'da README'dagi buyruqlarni to'g'ridan-to'g'ri ishlating.
COMPOSE := docker compose -f deploy/compose.yml
TEST    := docker compose -f deploy/compose.test.yml run --rm test

.PHONY: secrets lock build up down logs create-admin retire-keys rewrap-keys test lint typecheck etl-run seed-synthetic rollback-build fe-install fe-check web e2e

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

retire-keys: ## ishlatilmayotgan eski DEK'larni yo'q qilish (jadval egasi — migrate konteyneri)
	$(COMPOSE) run --rm migrate python -m app.cli retire-keys

rewrap-keys: ## KEK rotatsiyasi. make rewrap-keys f=/host/path/to/new_kek
	$(COMPOSE) run --rm -v "$(f):/tmp/new_kek:ro" migrate python -m app.cli rewrap-keys --new-kek-file /tmp/new_kek

test:
	$(TEST) pytest

lint:
	$(TEST) ruff check app tests

typecheck:
	$(TEST) mypy app

MODE ?= incremental

etl-run: ## make etl-run SOURCE=synthetic MODE=full
	$(COMPOSE) exec worker python -m app.cli etl-run --source "$(SOURCE)" --mode "$(MODE)"

seed-synthetic: ## dev: 2024-01-01 dan bugungacha sintetik ma'lumot
	$(COMPOSE) exec worker python -m app.cli etl-run --source synthetic --mode full

rollback-build: ## make rollback-build [BUILD=id]
	$(COMPOSE) exec worker python -m app.cli rollback-build $(if $(BUILD),--build $(BUILD),)

NODE := docker compose -f deploy/compose.frontend.yml run --rm node

fe-install: ## frontend bog'liqliklari (package-lock.json bo'yicha)
	$(NODE) npm ci

fe-check: ## tsc + eslint + vitest
	$(NODE) npm run check

web: ## frontend'ni qayta qurish va Caddy'ni yangilash
	$(COMPOSE) up -d --build caddy

e2e: ## Playwright E2E (dev stack ishlab turishi kerak)
	./scripts/e2e.sh

.PHONY: check-backend
check-backend: ## ruff + mypy + bandit + pip-audit + pytest (qamrov 85%/95%)
	scripts/check_backend.sh

.PHONY: check check-repo check-frontend hooks
check: ## barcha darvozalar: repo + backend + frontend (spec 10)
	scripts/check.sh
check-repo: ## gitleaks (butun tarix) + semgrep + hadolint
	scripts/check_repo.sh
check-frontend: ## tsc + eslint + vitest + npm audit
	scripts/check_frontend.sh
hooks: ## pre-commit hook'ni ulash
	git config core.hooksPath .githooks

.PHONY: db-smoke
db-smoke: ## DB image smoke-testi (profil, kengaytmalar, rollar, pgBackRest)
	scripts/tests/db_image_smoke.sh
