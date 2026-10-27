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
