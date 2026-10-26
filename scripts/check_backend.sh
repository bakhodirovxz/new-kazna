#!/usr/bin/env bash
# Backend sifat darvozalari (spec 10) — hammasi Docker'da, deploy/compose.test.yml orqali.
# Chegaralar: ruff, mypy --strict, bandit (-ll -ii), pip-audit, pytest qamrovi 85% / 95%.
# Faqat dev checkout'dan: test konteyneri repo'ni (deploy/secrets bo'lsa, u ham) read-only mount qiladi.
set -euo pipefail
cd "$(dirname "$0")/.."
TEST=(docker compose -f deploy/compose.test.yml run --rm -T test)
trap 'docker compose -f deploy/compose.test.yml down -v --remove-orphans >/dev/null 2>&1 || true' EXIT

docker compose -f deploy/compose.test.yml build test
echo "== ruff";      "${TEST[@]}" ruff check app tests tools
echo "== mypy";      "${TEST[@]}" mypy app tools
echo "== bandit";    "${TEST[@]}" bandit -q -r app tools -ll -ii
echo "== pip-audit"; "${TEST[@]}" sh -c 'cat /etc/ssl/certs/ca-certificates.crt certs/*.crt > /tmp/ca.pem 2>/dev/null; \
                       REQUESTS_CA_BUNDLE=/tmp/ca.pem pip-audit --strict --require-hashes --disable-pip \
                       -r requirements.txt --cache-dir /tmp/pip-audit --progress-spinner off'
echo "== pytest";    "${TEST[@]}" sh -c 'pytest --cov=app --cov-report=term-missing:skip-covered \
                       --cov-report=json:/tmp/coverage.json \
                     && python tools/coverage_gate.py /tmp/coverage.json --total 85 \
                          --package app/core=95 --package app/auth=95 --package app/dwh=95'
echo "check-backend: OK"
