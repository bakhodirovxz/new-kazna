import os
import stat
from pathlib import Path

import pytest

from tests.ops.repo import load_script

EXPECTED = {
    "master_kek", "blind_index_key", "session_pepper", "db_superuser_password",
    "db_migrator_password", "db_app_password", "db_etl_password", "redis_password",
    "smtp_password", "pgbackrest_cipher_pass", "onec_ca_bundle.pem",
}


def test_generates_all_secrets_once(tmp_path: Path) -> None:
    gen = load_script("scripts/gen_secrets.py", "gen_secrets")
    gen.main(tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == EXPECTED
    assert len((tmp_path / "pgbackrest_cipher_pass").read_text(encoding="ascii")) >= 40
    assert stat.S_IMODE(os.stat(tmp_path / "master_kek").st_mode) == 0o600


def test_existing_secrets_are_not_overwritten(tmp_path: Path) -> None:
    gen = load_script("scripts/gen_secrets.py", "gen_secrets")
    for name in EXPECTED:
        (tmp_path / name).write_text("keep", encoding="ascii")
    gen.main(tmp_path)
    for name in EXPECTED:
        assert (tmp_path / name).read_text(encoding="ascii") == "keep", name


def test_symlink_target_is_refused(tmp_path: Path) -> None:
    gen = load_script("scripts/gen_secrets.py", "gen_secrets")
    victim = tmp_path / "victim"
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "master_kek").symlink_to(victim)  # dangling
    with pytest.raises(SystemExit):
        gen.main(tmp_path / "secrets")
    assert not victim.exists()
