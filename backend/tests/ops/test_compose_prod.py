import re
from typing import Any

import pytest
import yaml

from tests.ops.repo import repo_path

SERVICES = {"db", "redis", "migrate", "api", "worker", "caddy", "backup"}
BACKEND = ("migrate", "api", "worker")
SECRET_WORDS = ("PASSWORD", "KEK", "PEPPER", "SECRET", "CIPHER", "TOKEN")


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(repo_path("deploy/compose.prod.yml").read_text(encoding="utf-8"))


def test_expected_services(compose: dict[str, Any]) -> None:
    assert set(compose["services"]) == SERVICES


def test_every_service_is_hardened(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        assert svc.get("read_only") is True, name
        assert svc.get("init") is True, f"{name}: init (zombie reaping)"
        assert svc.get("cap_drop") == ["ALL"], name
        assert "cap_add" not in svc and svc.get("privileged") is not True, name
        assert "no-new-privileges:true" in svc.get("security_opt", []), name
        assert int(svc.get("pids_limit", 0)) > 0, name
        assert svc.get("mem_limit") and svc.get("cpus"), name
        assert re.fullmatch(r"[1-9]\d*:[1-9]\d*", str(svc.get("user", ""))), f"{name}: user"
        assert svc["logging"]["driver"] == "json-file", name
        options = svc["logging"]["options"]
        assert options["max-size"] and options["max-file"], name
        assert svc.get("tmpfs"), name


def test_restart_policies(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        assert svc["restart"] == ("no" if name == "migrate" else "unless-stopped"), name


def test_healthchecks(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        if name == "migrate":
            assert svc["healthcheck"] == {"disable": True}
        else:
            assert svc["healthcheck"]["test"], name


def test_images_are_own_versioned_images(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        pattern = r"ugekazna-(db|redis|backend|web):\$\{UGK_VERSION:\?[^}]*\}"
        assert re.fullmatch(pattern, svc["image"]), name
        assert "build" not in svc, name


def test_no_source_bind_mounts(compose: dict[str, Any]) -> None:
    named = set(compose["volumes"])
    for name, svc in compose["services"].items():
        for volume in svc.get("volumes", []):
            assert volume.split(":", 1)[0] in named, f"{name}: {volume}"
    assert compose["services"]["caddy"]["configs"][0]["target"] == "/etc/caddy/Caddyfile"


def test_network_isolation(compose: dict[str, Any]) -> None:
    networks = compose["networks"]
    assert networks["backend"]["internal"] is True and networks["web"]["internal"] is True
    assert not networks["edge"].get("internal") and not networks["egress"].get("internal")
    expected = {
        "db": ["backend"], "redis": ["backend"], "migrate": ["backend"],
        "api": ["backend", "web"], "worker": ["backend", "egress"], "caddy": ["edge", "web"],
    }
    for name, nets in expected.items():
        assert sorted(compose["services"][name]["networks"]) == nets, name
    assert compose["services"]["backup"]["network_mode"] == "none"


def test_only_caddy_publishes_unprivileged_ports(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        if name != "caddy":
            assert "ports" not in svc, name
    targets = {port.rsplit(":", 1)[1] for port in compose["services"]["caddy"]["ports"]}
    assert targets == {"8443", "8080"}


def test_no_secrets_in_environment(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        for key, value in (svc.get("environment") or {}).items():
            if any(word in key.upper() for word in SECRET_WORDS):
                assert key.endswith("_FILE") and str(value).startswith("/run/secrets/"), (
                    f"{name}: {key}"
                )


def test_secrets_are_scoped(compose: dict[str, Any]) -> None:
    s = {name: set(svc.get("secrets", [])) for name, svc in compose["services"].items()}
    assert "db_migrator_password" not in s["api"] | s["worker"]
    assert s["caddy"] == {"tls_cert", "tls_key"}
    assert "tls_key" not in s["worker"] and "tls_cert" in s["worker"]
    assert s["backup"] == {"pgbackrest_cipher_pass"}
    assert "master_kek" not in s["db"] | s["redis"] | s["caddy"] | s["backup"]


def test_api_runs_four_uvicorn_workers(compose: dict[str, Any]) -> None:
    command = compose["services"]["api"]["command"]
    assert command[command.index("--workers") + 1] == "4"
    assert "--reload" not in command


def test_backend_services_run_in_prod_mode(compose: dict[str, Any]) -> None:
    for name in BACKEND:
        assert compose["services"][name]["environment"]["ENV"] == "prod", name


def test_backup_schedule_matches_script_defaults(compose: dict[str, Any]) -> None:
    env = compose["services"]["backup"]["environment"]
    assert env["BACKUP_FULL_AT"] == "2000"
    assert env["BACKUP_DIFF_AT"] == "0200 0800 1400"


def test_prod_env_example_documents_all_variables() -> None:
    raw = repo_path("deploy/compose.prod.yml").read_text(encoding="utf-8")
    used = set(re.findall(r"\$\{([A-Z0-9_]+)", raw)) - {"UGK_VERSION"}
    example = repo_path("deploy/prod.env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^([A-Z0-9_]+)=", example, re.M))
    assert used <= documented, sorted(used - documented)
