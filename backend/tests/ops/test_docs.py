"""docs/security va docs/ops: tarkib, ASCII nomlar, kod/testlarga havolalar (spec 3.8, 11, 12)."""

import re
from pathlib import Path

from tests.ops.repo import REPO

SECURITY = REPO / "docs/security"
OPS = REPO / "docs/ops"
SECURITY_DOCS = {
    "README.md", "threat-model.md", "cryptography.md", "key-management.md", "audit-log.md",
    "access-control.md", "data-classification.md", "sast-exceptions.md", "asvs-l2.md",
    "incident-response.md", "secure-configuration.md", "sbom.md",
}
OPS_DOCS = {
    "README.md", "host-hardening.md", "install-upgrade.md", "backup-restore.md", "monitoring.md",
    "load-test.md", "admin-guide.md", "user-guide.md",
}
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


def _ids(prefix: str, count: int) -> set[str]:
    return {f"{prefix}.{i}" for i in range(1, count + 1)}


# OWASP ASVS 4.0.3: L1 va L2 darajasidagi barcha talablar (faqat L3 va o'chirilganlar kirmaydi).
ASVS_L2 = (
    _ids("1.1", 7) | _ids("1.2", 4) | {"1.4.1", "1.4.4", "1.4.5"} | _ids("1.5", 4) | _ids("1.6", 4)
    | _ids("1.7", 2) | _ids("1.8", 2) | _ids("1.9", 2) | {"1.10.1"} | _ids("1.11", 2) | {"1.12.2"}
    | _ids("1.14", 6)
    | _ids("2.1", 12) | _ids("2.2", 3) | _ids("2.3", 3) | _ids("2.4", 5) | _ids("2.5", 7)
    | _ids("2.6", 3) | _ids("2.7", 6) | _ids("2.8", 6) | _ids("2.9", 3) | _ids("2.10", 4)
    | {"3.1.1"} | _ids("3.2", 4) | _ids("3.3", 4) | _ids("3.4", 5) | _ids("3.5", 3) | {"3.7.1"}
    | {"4.1.1", "4.1.2", "4.1.3", "4.1.5"} | _ids("4.2", 2) | _ids("4.3", 3)
    | _ids("5.1", 5) | _ids("5.2", 8) | _ids("5.3", 10) | _ids("5.4", 3) | _ids("5.5", 4)
    | _ids("6.1", 3) | _ids("6.2", 6) | _ids("6.3", 2) | _ids("6.4", 2)
    | _ids("7.1", 4) | _ids("7.2", 2) | {"7.3.1", "7.3.4"} | _ids("7.4", 3)
    | _ids("8.1", 4) | _ids("8.2", 3) | _ids("8.3", 8)
    | _ids("9.1", 3) | _ids("9.2", 4)
    | _ids("10.2", 2) | _ids("10.3", 3)
    | _ids("11.1", 8)
    | _ids("12.1", 3) | {"12.2.1"} | _ids("12.3", 6) | _ids("12.4", 2) | _ids("12.5", 2)
    | {"12.6.1"}
    | {"13.1.1", "13.1.3", "13.1.4", "13.1.5"} | {"13.2.1", "13.2.2", "13.2.3", "13.2.5", "13.2.6"}
    | _ids("13.3", 2) | _ids("13.4", 2)
    | _ids("14.1", 4) | _ids("14.2", 6) | {"14.3.2", "14.3.3"} | _ids("14.4", 7) | _ids("14.5", 4)
)
ASVS_STATUSES = {"Выполнено", "Частично", "Отклонение (обосновано)", "Н/П"}


def _asvs_rows() -> list[list[str]]:
    text = (SECURITY / "asvs-l2.md").read_text(encoding="utf-8")
    return [
        [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        for line in text.splitlines()
        if re.match(r"^\| \d+\.\d+\.\d+ \|", line)
    ]


def test_asvs_matrix_covers_all_level2_requirements() -> None:
    ids = [row[0] for row in _asvs_rows()]
    assert len(ids) == len(set(ids)), "takroriy talab ID"
    assert not ASVS_L2 - set(ids), sorted(ASVS_L2 - set(ids))


def test_asvs_statuses_are_known() -> None:
    for row in _asvs_rows():
        assert len(row) == 5, row
        assert row[2] in ASVS_STATUSES, row
        if row[2] != "Выполнено":
            assert row[3] not in ("", "—"), f"{row[0]}: sabab/amalga oshirish ko'rsatilmagan"


# Hujjatlardagi `kod` havolalari (README.md va asvs-l2.md shu testlarga tayanadi).
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_TEST_NAME = re.compile(r"test_\w+")
_REPO_PATH = re.compile(
    r"(?:(?:backend|frontend|deploy|scripts|docs|loadtest|\.github|\.githooks)/[\w./-]+"
    r"|Makefile|\.gitlab-ci\.yml|\.gitleaks\.toml|\.trivyignore)"
)
# Reliz mashinasida yaratiladigan fayllar.
_HOST_FILES = {"deploy/prod.env", "deploy/release.env", "deploy/secrets", "build"}


def _spans() -> list[tuple[str, str]]:
    return [
        (doc.name, span)
        for doc in _docs()
        for span in _CODE_SPAN.findall(doc.read_text(encoding="utf-8"))
    ]


def test_cited_tests_exist() -> None:
    defined = {
        name
        for path in (REPO / "backend/tests").rglob("*.py")
        for name in re.findall(r"^\s*(?:async )?def (test_\w+)\(", path.read_text("utf-8"), re.M)
    }
    cited = {(doc, span) for doc, span in _spans() if _TEST_NAME.fullmatch(span)}
    missing = sorted(item for item in cited if item[1] not in defined)
    assert not missing, missing


def test_cited_paths_exist() -> None:
    missing = []
    for doc, span in _spans():
        token = re.sub(r":\d+(?:-\d+)?$", "", span)
        path = token.rstrip("/")
        skipped = path in _HOST_FILES or path.startswith(("deploy/secrets/", "build/"))
        if not _REPO_PATH.fullmatch(token) or skipped:
            continue
        if not (REPO / token).exists():
            missing.append((doc, token))
    assert not missing, sorted(set(missing))


def test_host_hardening_covers_required_controls() -> None:
    text = (OPS / "host-hardening.md").read_text(encoding="utf-8")
    for needle in ("LUKS2", "aes-xts-plain64", "ufw", "DOCKER-USER", "PasswordAuthentication no",
                   "auditd", "chrony", "unattended-upgrades", '"userns-remap"', '"live-restore"',
                   '"no-new-privileges"', "max-size", "ugk-admins", "SIEM"):
        assert needle in text, needle


MD_LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")


def test_relative_links_resolve() -> None:
    missing = [
        f"{doc.name}: {target}"
        for doc in _docs()
        for target in MD_LINK.findall(doc.read_text(encoding="utf-8"))
        if not (doc.parent / target).exists()
    ]
    assert not missing, missing


def test_user_guide_is_three_to_five_pages() -> None:
    words = len(re.findall(r"\w+", (OPS / "user-guide.md").read_text(encoding="utf-8")))
    assert 900 <= words <= 2200, words  # ~300-500 so'z sahifasiga -> 3-5 sahifa (TZ 10)
