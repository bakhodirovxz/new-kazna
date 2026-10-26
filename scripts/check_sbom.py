"""SBOM tekshiruvi (spec 10; ASVS 14.2.5): CycloneDX formati, bo'sh emas, kutilgan komponentlar bor.

    python scripts/check_sbom.py build/sbom/*.cdx.json
Chiqish kodi: 0 — hammasi to'g'ri, 1 — xato topildi, 2 — fayl berilmagan.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# Fayl nomi (".cdx.json" siz) → albatta bo'lishi kerak bo'lgan komponentlar (kichik harf).
REQUIRED: dict[str, set[str]] = {
    "ugekazna-backend": {"fastapi", "cryptography", "argon2-cffi"},
    "ugekazna-db": {"pgbackrest"},
    "ugekazna-web": set(),
    "ugekazna-redis": set(),
    "frontend-npm": {"react", "react-dom"},
}


def _names(components: list[dict[str, Any]]) -> Iterator[str]:
    for component in components:
        yield str(component.get("name", "")).lower()
        yield from _names(component.get("components", []))


def check(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{path.name}: o'qib bo'lmadi ({exc})"]
    errors: list[str] = []
    if data.get("bomFormat") != "CycloneDX":
        errors.append(f"{path.name}: bomFormat CycloneDX emas")
    names = set(_names(data.get("components", [])))
    if not names:
        errors.append(f"{path.name}: komponentlar yo'q")
    missing = REQUIRED.get(path.name.removesuffix(".cdx.json"), set()) - names
    if missing:
        errors.append(f"{path.name}: kutilgan komponentlar yo'q: {', '.join(sorted(missing))}")
    return errors


def main(argv: list[str]) -> int:
    if not argv:
        sys.stdout.write("Foydalanish: check_sbom.py <fayl.cdx.json>...\n")
        return 2
    errors = [error for arg in argv for error in check(Path(arg))]
    for error in errors:
        sys.stdout.write(error + "\n")
    if not errors:
        sys.stdout.write(f"OK: {len(argv)} ta SBOM tekshirildi\n")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
