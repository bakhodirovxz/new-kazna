"""deploy/secrets/ ichida barcha sirlarni yaratadi. Mavjud fayllarga tegmaydi.

Ishlatish:  python scripts/gen_secrets.py [papka]
Prod (Linux): keyin  sudo scripts/secrets_perms.sh <papka>
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
    "pgbackrest_cipher_pass",
)
# Ichki SMTP relay parolsiz bo'lsa bo'sh qoladi; kerak bo'lsa operator to'ldiradi.
EMPTY_OPTIONAL = ("smtp_password",)


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
    for name in EMPTY_OPTIONAL:
        _write(target / name, "")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("deploy/secrets"))
