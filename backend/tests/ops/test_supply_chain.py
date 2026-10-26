import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.ops.repo import load_script, repo_path

REQUIRED = {
    "PYTHON_IMAGE",
    "NODE_IMAGE",
    "CADDY_IMAGE",
    "CADDY_BUILDER_IMAGE",
    "POSTGRES_IMAGE",
    "REDIS_IMAGE",
}
PINNED = re.compile(r"^[a-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")


def _lock() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in repo_path("deploy/images.lock.env").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key] = value
    return out


def test_base_images_pinned_by_digest() -> None:
    lock = _lock()
    assert set(lock) == REQUIRED
    for key, ref in lock.items():
        assert PINNED.match(ref), f"{key}={ref}"


@pytest.mark.parametrize(
    ("dockerfile", "args"),
    [
        ("backend/Dockerfile", {"PYTHON_IMAGE"}),
        ("frontend/Dockerfile", {"NODE_IMAGE", "CADDY_IMAGE", "CADDY_BUILDER_IMAGE"}),
        ("deploy/postgres/Dockerfile", {"POSTGRES_IMAGE"}),
    ],
)
def test_dockerfiles_use_pinned_args(dockerfile: str, args: set[str]) -> None:
    text = repo_path(dockerfile).read_text(encoding="utf-8")
    froms = re.findall(r"^FROM\s+(\S+)", text, re.M)
    assert froms and all(ref.startswith("${") for ref in froms), froms
    assert args <= set(re.findall(r"^ARG\s+([A-Z_]+)=", text, re.M))
    # Har `FROM ${…}` ustida qator bo'yicha hadolint istisnosi (global ignore yo'q).
    assert len(re.findall(r"^# hadolint ignore=DL3006\nFROM \$\{", text, re.M)) == len(froms)


def _bom(path: Path, components: list[dict[str, Any]], fmt: str = "CycloneDX") -> Path:
    path.write_text(
        json.dumps({"bomFormat": fmt, "specVersion": "1.5", "components": components}),
        encoding="utf-8",
    )
    return path


def _generic(name: str, version: str) -> dict[str, Any]:
    return {"name": name, "version": version, "purl": f"pkg:generic/{name}@{version}"}


def test_check_sbom_accepts_valid(tmp_path: Path) -> None:
    check_sbom = load_script("scripts/check_sbom.py", "check_sbom")
    ok = _bom(
        tmp_path / "ugekazna-backend.cdx.json",
        [{"name": "fastapi"}, {"name": "argon2-cffi"}, _generic("python", "3.12.15"),
         {"name": "opt/venv", "components": [{"name": "cryptography"}]}],
    )
    assert check_sbom.check(ok) == []
    assert check_sbom.main([str(ok)]) == 0


def test_check_sbom_rejects_invalid(tmp_path: Path) -> None:
    check_sbom = load_script("scripts/check_sbom.py", "check_sbom")
    missing = _bom(tmp_path / "frontend-npm.cdx.json", [{"name": "lodash"}])
    wrong = _bom(tmp_path / "ugekazna-redis.cdx.json", [{"name": "redis"}], fmt="SPDX")
    empty = _bom(tmp_path / "ugekazna-web.cdx.json", [])
    errors = check_sbom.check(missing) + check_sbom.check(wrong) + check_sbom.check(empty)
    assert any("react" in e for e in errors)
    assert any("CycloneDX" in e for e in errors)
    assert any("komponent" in e for e in errors)
    assert check_sbom.main([str(missing)]) == 1
    assert check_sbom.main([]) == 2


def test_check_sbom_group_and_shape(tmp_path: Path) -> None:
    check_sbom = load_script("scripts/check_sbom.py", "check_sbom")
    scoped = _bom(
        tmp_path / "frontend-npm.cdx.json",
        [{"group": "@types", "name": "react"}, {"name": "react-dom"}],
    )
    assert any("react" in e for e in check_sbom.check(scoped))  # @types/react != react
    # apk virtual `postgresql` (noarch) PG16 runtime komponentini almashtirmaydi.
    db = _bom(
        tmp_path / "ugekazna-db.cdx.json",
        [{"name": "pgbackrest"}, {"name": "postgresql", "version": "20261026"}],
    )
    assert any("pkg:generic/postgresql" in e for e in check_sbom.check(db))
    notobj = tmp_path / "ugekazna-redis.cdx.json"
    notobj.write_text("[]", encoding="utf-8")
    assert check_sbom.check(notobj) == [f"{notobj.name}: JSON ob'ekt emas"]


def test_sbom_runtime_adds_components(tmp_path: Path) -> None:
    sbom_runtime = load_script("scripts/sbom_runtime.py", "sbom_runtime")
    check_sbom = load_script("scripts/check_sbom.py", "check_sbom")
    path = _bom(tmp_path / "ugekazna-redis.cdx.json", [{"name": "musl"}])
    assert sbom_runtime.main([str(path), "redis=7.4.12"]) == 0
    assert sbom_runtime.main([str(path), "redis=7.4.13"]) == 0  # almashtiriladi, ko'paymaydi
    assert check_sbom.check(path) == []
    redis = [c for c in json.loads(path.read_text("utf-8"))["components"] if c["name"] == "redis"]
    assert [c["version"] for c in redis] == ["7.4.13"]
    assert sbom_runtime.main([str(path), "redis="]) == 1  # bo'sh env — yiqiladi
    assert sbom_runtime.main([]) == 2


def test_lock_keys_match_consumers() -> None:
    lock = set(_lock())
    build = repo_path("scripts/build_images.sh").read_text(encoding="utf-8")
    # REDIS_IMAGE Dockerfile'ga berilmaydi (faqat qayta teglanadi).
    for key in lock - {"REDIS_IMAGE"}:
        assert f'--build-arg "{key}=${key}"' in build, key
    assert '"ugekazna-redis:$VERSION"' in build
    pin = repo_path("scripts/pin_images.sh").read_text(encoding="utf-8")
    assert set(re.findall(r'^\s+"([A-Z_]+)=', pin, re.M)) == lock


def test_release_builds_from_clean_export() -> None:
    text = repo_path("scripts/release.sh").read_text(encoding="utf-8")
    assert "git archive HEAD | tar -x" in text
    # scan/build faqat eksport ichida; ishchi daraxtdagi scripts/scan.sh chaqirilmaydi.
    assert '(cd "$SRC" && scripts/scan.sh "$VERSION")' in text
    assert not re.search(r"^scripts/scan\.sh", text, re.M)
    assert "git ls-tree -r --name-only HEAD" in text  # eksport == HEAD o'z-o'zini tekshirish
    # Yetishmayotgan majburiy yo'l — xato (fail-closed), ogohlantirish emas.
    assert "! -e \"$SRC/$path\"" in text
    assert re.search(r"XATO: \$path[^\n]*\n\s+exit 1", text)
