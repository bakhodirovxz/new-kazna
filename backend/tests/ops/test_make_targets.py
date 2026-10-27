import re

from tests.ops.repo import REPO, repo_path

SPEC_TARGETS = {  # spec 11 (anonymize-copy — ongli chetlanish, spec 14-bo'lim)
    "up", "down", "migrate", "seed-synthetic", "create-admin", "etl-run", "rollback-build",
    "backup", "restore-test", "rotate-keys", "audit-verify", "check", "scan",
}
WINDOWS_TARGETS = {
    "help", "secrets", "build", "up", "down", "logs", "web", "create-admin", "seed-synthetic",
    "audit-verify", "rotate-keys", "ops-check", "test", "lint", "typecheck", "check",
    "check-backend", "check-frontend", "check-repo", "hooks", "fe-install", "fe-check", "e2e",
    "pin-images", "scan", "release", "prod-config", "test-caddy", "db-smoke", "backup-selftest",
    "load-test",
}
BASE_TARGETS = {  # Makefile @ c331568: bitta ham yo'qolmasligi kerak (regressiya qo'riqchisi)
    "secrets", "lock", "build", "up", "down", "logs", "create-admin", "retire-keys",
    "rewrap-keys", "test", "lint", "typecheck", "etl-run", "seed-synthetic", "rollback-build",
    "fe-install", "fe-check", "web", "e2e", "e2e-ci", "check-backend", "check", "check-repo",
    "check-frontend", "hooks", "db-smoke", "pin-images", "scan", "release", "prod-config",
    "test-caddy", "load-test", "backup", "backup-status", "restore-test", "backup-selftest",
    "monitor",
}


def _make_targets() -> tuple[set[str], set[str]]:
    text = repo_path("Makefile").read_text(encoding="utf-8")
    defined = set(re.findall(r"^([a-z0-9-]+):", text, re.M))
    documented = set(re.findall(r"^([a-z0-9-]+):.*## ", text, re.M))
    return defined, documented


def _ps1_targets() -> set[str]:
    text = repo_path("scripts/dev.ps1").read_text(encoding="utf-8")
    return set(re.findall(r'^\s+"([a-z0-9-]+)"\s*\{', text, re.M))


def test_spec_targets_present() -> None:
    defined, _ = _make_targets()
    assert defined >= SPEC_TARGETS, sorted(SPEC_TARGETS - defined)


def test_base_targets_survive() -> None:
    defined, _ = _make_targets()
    assert defined >= BASE_TARGETS, sorted(BASE_TARGETS - defined)


def test_every_make_target_has_help() -> None:
    defined, documented = _make_targets()
    assert defined == documented, sorted(defined - documented)


def test_windows_script_covers_make_targets() -> None:
    defined, _ = _make_targets()
    ps1 = _ps1_targets()
    assert ps1 >= WINDOWS_TARGETS, sorted(WINDOWS_TARGETS - ps1)
    assert ps1 <= defined, sorted(ps1 - defined)
    assert repo_path("scripts/dev.ps1").read_text(encoding="utf-8").isascii()


def test_shell_scripts_have_shebang_and_lf() -> None:
    scripts = [
        *REPO.glob("scripts/*.sh"),
        *REPO.glob("scripts/tests/*.sh"),
        *REPO.glob("scripts/ops/*.sh"),
        *REPO.glob("deploy/postgres/bin/*"),
        *REPO.glob("deploy/pgbackrest/bin/ugk-backup"),
        *REPO.glob("deploy/pgbackrest/bin/ugk-restore"),
        REPO / ".githooks/pre-commit",
    ]
    assert len(scripts) >= 15
    for script in scripts:
        data = script.read_bytes()
        assert data.startswith(b"#!"), script
        assert b"\r\n" not in data, script
