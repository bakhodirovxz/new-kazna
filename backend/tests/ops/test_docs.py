"""docs/security va docs/ops: tarkib, ASCII nomlar, kod/testlarga havolalar (spec 3.8, 11, 12)."""

import re
from pathlib import Path

from tests.ops.repo import REPO

SECURITY = REPO / "docs/security"
OPS = REPO / "docs/ops"
SECURITY_DOCS = {
    "README.md", "threat-model.md", "cryptography.md", "key-management.md", "audit-log.md",
    "access-control.md", "data-classification.md", "sast-exceptions.md",
}
OPS_DOCS: set[str] = set()
STRIDE = ("Spoofing", "Tampering", "Repudiation", "Information disclosure", "Denial of service",
          "Elevation of privilege")


def _docs() -> list[Path]:
    return sorted([*SECURITY.glob("*.md"), *OPS.glob("*.md")])


def test_required_docs_exist() -> None:
    for folder, names in ((SECURITY, SECURITY_DOCS), (OPS, OPS_DOCS)):
        missing = sorted(name for name in names if not (folder / name).is_file())
        assert not missing, (folder.name, missing)


def test_doc_file_names_are_ascii() -> None:
    assert all(path.name.isascii() for path in _docs())


def test_threat_model_has_dfd_and_stride() -> None:
    text = (SECURITY / "threat-model.md").read_text(encoding="utf-8")
    assert "```mermaid" in text
    for word in STRIDE:
        assert word in text, word
    assert len(re.findall(r"^\| S\d+ \|", text, re.M)) >= 25
