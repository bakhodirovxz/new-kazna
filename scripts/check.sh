#!/usr/bin/env bash
# make check (spec 10): repo skanerlari + backend + frontend. Birinchi xatoda to'xtaydi.
set -euo pipefail
cd "$(dirname "$0")/.."
scripts/check_repo.sh
scripts/check_backend.sh
scripts/check_frontend.sh
echo "make check: hammasi yashil"
