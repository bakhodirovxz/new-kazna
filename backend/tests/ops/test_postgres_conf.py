import itertools
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.ops.repo import repo_path

PG = "deploy/postgres"
BACKUP = "deploy/pgbackrest/bin/ugk-backup"
ENV_LIB = "deploy/pgbackrest/bin/ugk-pgbackrest-env"
_UNIT_KB = {"kB": 1, "MB": 1024, "GB": 1024 * 1024}


def parse_conf(relative: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in repo_path(relative).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("include "):
            key, _, value = line.partition(" ")
        else:
            key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip("'")
    return out


def kb(value: str) -> int:
    match = re.fullmatch(r"(\d+)(kB|MB|GB)", value)
    assert match, value
    return int(match.group(1)) * _UNIT_KB[match.group(2)]


def _sh(
    script: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    full_env = {**os.environ, "UGK_PGBR_ENV": str(repo_path(ENV_LIB)), **(env or {})}
    return subprocess.run(
        ["sh", str(repo_path(script)), *args],
        capture_output=True, text=True, env=full_env, check=False,
    )


def test_postgresql_conf_security_settings() -> None:
    conf = parse_conf(f"{PG}/postgresql.conf")
    assert conf["password_encryption"] == "scram-sha-256"
    assert conf["shared_preload_libraries"] == "pg_stat_statements,auto_explain"
    assert conf["log_min_duration_statement"] == "500ms"
    assert conf["random_page_cost"] == "1.1"
    assert conf["archive_mode"] == "on"
    assert conf["archive_timeout"] == "15min"
    assert conf["archive_command"] == "pgbackrest --stanza=ugk archive-push %p"
    assert conf["ssl"] == "off"
    assert conf["hba_file"] == "/etc/postgresql/pg_hba.conf"
    assert conf["timezone"] == "UTC"
    assert conf["log_timezone"] == "UTC"
    assert conf["include"] == "/tmp/pg-profile.conf"
    assert conf["log_connections"] == "on"
    assert conf["log_disconnections"] == "on"
    assert conf["idle_in_transaction_session_timeout"] == "60s"
    assert conf["listen_addresses"] == "*"
    assert conf["log_statement"] == "ddl"
    # bog'langan parametrlar (PII/sir) loglarga tushmasin
    assert conf["log_parameter_max_length"] == "0"
    assert conf["log_parameter_max_length_on_error"] == "0"
    assert conf["auto_explain.log_parameter_max_length"] == "0"


def test_profiles_do_not_override_security_keys() -> None:
    denied = re.compile(
        r"^(ssl.*|password_encryption|log_.*|.*log_parameter.*|listen_addresses|hba_file|archive_.*"
        r"|shared_preload_libraries|include)$"
    )
    for name in ("ci", "8gb", "16gb"):
        bad = [k for k in parse_conf(f"{PG}/profiles/{name}.conf") if denied.match(k)]
        assert not bad, (name, bad)


def test_max_connections_covers_pools() -> None:
    conf = parse_conf(f"{PG}/postgresql.conf")
    pool = 10 + 10  # Settings.db_pool_size + max_overflow (backend/app/core/db.py)
    # api: 4 uvicorn worker; worker: app + etl engine; migrate/backup/restore/psql: 5
    needed = 4 * pool + 2 * pool + 5 + int(conf["superuser_reserved_connections"])
    assert int(conf["max_connections"]) >= needed


def test_profiles_scale_with_memory() -> None:
    profiles = {name: parse_conf(f"{PG}/profiles/{name}.conf") for name in ("ci", "8gb", "16gb")}
    for key in ("shared_buffers", "effective_cache_size", "work_mem", "maintenance_work_mem"):
        assert kb(profiles["ci"][key]) < kb(profiles["8gb"][key]) < kb(profiles["16gb"][key]), key
    # shared_buffers ≤ 25% DB konteyner limiti (8gb → UGK_DB_MEM=4g, 16gb → 9g)
    assert kb(profiles["8gb"]["shared_buffers"]) <= 4 * 1024 * 1024 // 4
    assert kb(profiles["16gb"]["shared_buffers"]) <= 9 * 1024 * 1024 // 4


def test_pg_hba_only_scram_and_reject() -> None:
    rules = [
        line.split()
        for line in repo_path(f"{PG}/pg_hba.conf").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert {rule[-1] for rule in rules} <= {"peer", "scram-sha-256", "reject"}
    assert ["local", "all", "postgres", "peer"] in rules
    host_rules = [rule for rule in rules if rule[0] == "host"]
    for rule in host_rules:
        if rule[-1] != "reject":
            assert rule[1] != "all", rule
            assert rule[3] == "samenet" and rule[2] != "all" and "postgres" not in rule[2], rule
    assert host_rules[-1][-1] == "reject"


def test_pgbackrest_conf_encrypted_without_password() -> None:
    text = repo_path("deploy/pgbackrest/pgbackrest.conf").read_text(encoding="utf-8")
    assert "repo1-cipher-type=aes-256-cbc" in text
    assert "repo1-retention-full=14" in text
    assert "repo1-retention-diff=12" in text
    assert not re.search(r"^\s*repo1-cipher-pass", text, re.M)
    assert "[ugk]" in text
    assert "pg1-path=/var/lib/postgresql/data" in text


@pytest.mark.parametrize(
    ("slot", "kind"),
    [("2000", "full"), ("0200", "diff"), ("0800", "diff"), ("1400", "diff"), ("1234", "none"),
     ("0000", "none")],
)
def test_backup_schedule_slots(slot: str, kind: str) -> None:
    result = _sh(BACKUP, "due", slot)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == kind


def test_backup_schedule_meets_rpo_gaps() -> None:
    text = repo_path(BACKUP).read_text(encoding="utf-8")
    full = re.search(r"BACKUP_FULL_AT:=([0-9 ]+)\}", text)
    diff = re.search(r"BACKUP_DIFF_AT:=([0-9 ]+)\}", text)
    assert full and diff
    slots = (full.group(1) + " " + diff.group(1)).split()
    minutes = sorted(int(s[:2]) * 60 + int(s[2:]) for s in slots)
    gaps = [b - a for a, b in itertools.pairwise(minutes)] + [minutes[0] + 1440 - minutes[-1]]
    assert max(gaps) <= 6 * 60


def test_entrypoint_rejects_unknown_profile() -> None:
    result = _sh(f"{PG}/bin/ugk-db-entrypoint", "postgres", env={"UGK_PG_PROFILE": "32gb"})
    assert result.returncode == 1
    assert "UGK_PG_PROFILE" in result.stderr


def _stub_pgbackrest(tmp_path: Path, code: int) -> dict[str, str]:
    # Funksiya-stublar (tmp noexec bo'lishi mumkin). jq "muvaffaqiyatli": quvur pgbackrest
    # xatosini yashirmasligi kerak.
    env_stub = tmp_path / "env.sh"
    env_stub.write_text(
        "ugk_cipher_conf() { :; }\n"
        f"pgbackrest() {{ echo boom >&2; return {code}; }}\n"
        "jq() { cat >/dev/null; echo X; }\n",
        encoding="ascii",
    )
    return {"UGK_PGBR_ENV": str(env_stub)}


@pytest.mark.parametrize("command", ["latest", "health", "info"])
def test_backup_does_not_mask_pgbackrest_failure(tmp_path: Path, command: str) -> None:
    result = _sh(BACKUP, command, env=_stub_pgbackrest(tmp_path, 7))
    assert result.returncode != 0, (result.stdout, result.stderr)


@pytest.mark.parametrize("content", [None, "", "\n", "a\nb\n"])
def test_entrypoint_fails_closed_without_valid_cipher_secret(
    tmp_path: Path, content: str | None
) -> None:
    secret = tmp_path / "cipher"
    if content is not None:
        secret.write_text(content, encoding="ascii")
    result = _sh(
        f"{PG}/bin/ugk-db-entrypoint", "postgres", "-c", "config_file=/x",
        env={"UGK_PG_PROFILE": "ci", "UGK_CIPHER_SECRET": str(secret)},
    )
    assert result.returncode == 1, result.stderr
    assert "pgbackrest_cipher_pass" in result.stderr


def test_entrypoint_requires_config_file() -> None:
    result = _sh(f"{PG}/bin/ugk-db-entrypoint", "postgres", env={"UGK_PG_PROFILE": "ci"})
    assert result.returncode == 1
    assert "config_file" in result.stderr


def test_restore_fails_closed_on_missing_data_dir(tmp_path: Path) -> None:
    stub = tmp_path / "env.sh"
    stub.write_text("ugk_cipher_conf() { :; }\n", encoding="ascii")
    result = _sh(
        "deploy/pgbackrest/bin/ugk-restore",
        env={"UGK_PGBR_ENV": str(stub), "PGDATA": str(tmp_path / "nope")},
    )
    assert result.returncode == 3


def test_restore_refuses_non_empty_data_dir(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "PG_VERSION").write_text("16\n", encoding="ascii")
    stub = tmp_path / "env.sh"
    stub.write_text("ugk_cipher_conf() { :; }\n", encoding="ascii")
    result = _sh(
        "deploy/pgbackrest/bin/ugk-restore", env={"UGK_PGBR_ENV": str(stub), "PGDATA": str(data)}
    )
    assert result.returncode == 3
    assert "bo'sh emas" in result.stderr


def test_initdb_roles_do_not_log_passwords() -> None:
    text = repo_path(f"{PG}/initdb/01-roles.sh").read_text(encoding="utf-8")
    body = [line.strip() for line in text.split("<<'SQL'", 1)[1].splitlines() if line.strip()]
    assert body[:2] == ["SET log_statement = 'none';", "SET log_min_duration_statement = -1;"]


def test_dockerignore_excludes_secrets() -> None:
    lines = [
        line.strip()
        for line in repo_path("deploy/.dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert lines[0] == "*"
    assert set(lines[1:]) == {"!postgres", "!pgbackrest"}
