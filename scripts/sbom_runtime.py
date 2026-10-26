"""SBOM'ga runtime komponentlarini qo'shish (rasmiy image'lar CPython/PostgreSQL/Redis/Caddy'ni manbadan
quradi — Trivy paket metama'lumotini ko'rmaydi). Versiya image env'idan olinadi.

    python scripts/sbom_runtime.py build/sbom/x.cdx.json python=3.12.15 [nom=versiya ...]
Chiqish kodi: 0 — qo'shildi, 1 — noto'g'ri kirish (bo'sh versiya, JSON ob'ekt emas), 2 — argument yo'q.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def add(path: Path, pairs: list[str]) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return [f"{path.name}: JSON ob'ekt emas"]
    components = data.setdefault("components", [])
    errors: list[str] = []
    for pair in pairs:
        name, _, version = pair.partition("=")
        if not name or not version:
            errors.append(f"{path.name}: '{pair}' — nom=versiya kerak (env o'zgaruvchisi bo'sh?)")
            continue
        purl = f"pkg:generic/{name}@{version}"
        components[:] = [c for c in components if not str(c.get("purl", "")).startswith(
            f"pkg:generic/{name}@")]
        components.append(
            {"type": "application", "name": name, "version": version, "purl": purl,
             "bom-ref": purl}
        )
    if not errors:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stdout.write("Foydalanish: sbom_runtime.py <fayl.cdx.json> nom=versiya...\n")
        return 2
    errors = add(Path(argv[0]), argv[1:])
    for error in errors:
        sys.stdout.write(error + "\n")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
