# Linux/prod uchun. Windows'da README'dagi buyruqlarni to'g'ridan-to'g'ri ishlating.
COMPOSE := docker compose -f deploy/compose.yml
TEST    := docker compose -f deploy/compose.test.yml run --rm test

.PHONY: secrets lock build up down logs create-admin retire-keys rewrap-keys test lint typecheck

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
