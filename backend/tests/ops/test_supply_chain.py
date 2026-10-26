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


def test_check_sbom_accepts_valid(tmp_path: Path) -> None:
    check_sbom = load_script("scripts/check_sbom.py", "check_sbom")
    ok = _bom(
        tmp_path / "ugekazna-backend.cdx.json",
        [{"name": "fastapi"}, {"name": "argon2-cffi"},
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
