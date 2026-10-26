import os
import stat
from pathlib import Path

from tests.ops.repo import load_script

EXPECTED = {
    "master_kek", "blind_index_key", "session_pepper", "db_superuser_password",
    "db_migrator_password", "db_app_password", "db_etl_password", "redis_password",
    "smtp_password", "pgbackrest_cipher_pass",
}


def test_generates_all_secrets_once(tmp_path: Path) -> None:
    gen = load_script("scripts/gen_secrets.py", "gen_secrets")
    gen.main(tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == EXPECTED
    assert len((tmp_path / "pgbackrest_cipher_pass").read_text(encoding="ascii")) >= 40
    assert stat.S_IMODE(os.stat(tmp_path / "master_kek").st_mode) == 0o600


def test_existing_secrets_are_not_overwritten(tmp_path: Path) -> None:
    gen = load_script("scripts/gen_secrets.py", "gen_secrets")
    (tmp_path / "pgbackrest_cipher_pass").write_text("keep", encoding="ascii")
    gen.main(tmp_path)
    assert (tmp_path / "pgbackrest_cipher_pass").read_text(encoding="ascii") == "keep"
