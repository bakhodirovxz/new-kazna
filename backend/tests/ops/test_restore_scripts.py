import re
from typing import Any

import yaml

from tests.ops.repo import repo_path


def _yaml(relative: str) -> Any:
    return yaml.safe_load(repo_path(relative).read_text(encoding="utf-8"))


def test_restore_compose_is_isolated() -> None:
    compose = _yaml("deploy/compose.restore.yml")
    assert compose["networks"]["restore"]["internal"] is True
    assert compose["volumes"]["pgbackrest_repo"]["external"] is True
    assert "pgbackrest_repo:/var/lib/pgbackrest:ro" in compose["services"]["restore-db"]["volumes"]
    for name, svc in compose["services"].items():
        assert svc["networks"] == ["restore"] and "ports" not in svc, name
        assert svc["read_only"] is True and svc["cap_drop"] == ["ALL"], name
        assert svc["restart"] == "no", name


def test_restore_disables_archiving() -> None:
    compose = _yaml("deploy/compose.restore.yml")
    assert "archive_mode=off" in compose["services"]["restore-db"]["command"]
    restore = repo_path("deploy/pgbackrest/bin/ugk-restore").read_text(encoding="utf-8")
    assert "--archive-mode=off" in restore
    script = repo_path("scripts/restore_test.sh").read_text(encoding="utf-8")
    assert "SHOW archive_mode" in script
    assert "restore-test-record" in script


def test_monitor_covers_all_long_running_services() -> None:
    compose = _yaml("deploy/compose.prod.yml")
    text = repo_path("scripts/ops/monitor.sh").read_text(encoding="utf-8")
    match = re.search(r"^SERVICES=\(([^)]*)\)", text, re.M)
    assert match
    assert set(match.group(1).split()) == set(compose["services"]) - {"migrate"}


def test_timers_schedule() -> None:
    monitor = repo_path("deploy/systemd/ugekazna-monitor.timer").read_text(encoding="utf-8")
    restore = repo_path("deploy/systemd/ugekazna-restore-test.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*:0/15" in monitor
    assert "OnCalendar=Sat *-*-01..07 21:00:00 Asia/Tashkent" in restore
    assert "Persistent=true" in monitor and "Persistent=true" in restore


def test_restore_script_always_records_valid_label() -> None:
    script = repo_path("scripts/restore_test.sh").read_text(encoding="utf-8")
    assert "BACKUP_LABEL=none" in script and "[[ $BACKUP_LABEL =~" in script
    assert '"--set=$BACKUP_LABEL"' in script  # yozilgan yorliq == tiklangan zaxira
    assert "code=1" in script  # yozuv yozilmasa, chiqish kodi 0 bo'lmaydi


def test_services_have_timeout_hardening_and_alert() -> None:
    services = sorted(repo_path("deploy/systemd").glob("*.service"))
    assert len(services) == 3
    for unit in services:
        text = unit.read_text(encoding="utf-8")
        assert re.search(r"^TimeoutStartSec=", text, re.M), unit.name
        for key in ("NoNewPrivileges=yes", "PrivateTmp=yes", "ProtectHome=read-only",
                    "ProtectSystem=full"):
            assert key in text, (unit.name, key)
    for name in ("monitor", "restore-test"):
        text = repo_path(f"deploy/systemd/ugekazna-{name}.service").read_text(encoding="utf-8")
        assert "OnFailure=ugekazna-alert@%n.service" in text
        for key in ("ProtectKernelTunables=yes", "ProtectKernelModules=yes",
                    "RestrictSUIDSGID=yes", "LockPersonality=yes"):
            assert key in text, (name, key)
    alert = repo_path("deploy/systemd/ugekazna-alert@.service").read_text(encoding="utf-8")
    assert "logger" in alert and "user.crit" in alert and "%i" in alert
    monitor = repo_path("deploy/systemd/ugekazna-monitor.service").read_text(encoding="utf-8")
    assert "TimeoutStartSec=10min" in monitor


def test_monitor_logs_critical_when_mail_path_down() -> None:
    text = repo_path("scripts/ops/monitor.sh").read_text(encoding="utf-8")
    assert "user.crit" in text and 'state="ps xatosi"' in text
