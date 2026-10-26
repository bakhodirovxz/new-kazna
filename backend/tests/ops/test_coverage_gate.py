import json
from pathlib import Path
from typing import Any

import pytest

from tools.coverage_gate import GateResult, evaluate, main, package_percent


def _report() -> dict[str, Any]:
    files = {
        "app/core/crypto.py": {"summary": {"covered_lines": 96, "num_statements": 100}},
        "app/core/db.py": {"summary": {"covered_lines": 50, "num_statements": 50}},
        "app/auth/service.py": {"summary": {"covered_lines": 90, "num_statements": 100}},
        "app\\dwh\\builds.py": {"summary": {"covered_lines": 100, "num_statements": 100}},
        "app/etl/runner.py": {"summary": {"covered_lines": 60, "num_statements": 100}},
    }
    return {"files": files, "totals": {"covered_lines": 396, "num_statements": 450}}


def test_gate_passes_when_all_thresholds_met() -> None:
    results = evaluate(_report(), 85, {"app/core": 95, "app/dwh": 95})
    assert [r.name for r in results] == ["TOTAL", "app/core", "app/dwh"]
    assert all(r.ok for r in results)
    assert results[1].percent == pytest.approx(146 / 150 * 100)


def test_gate_fails_below_package_threshold() -> None:
    auth = evaluate(_report(), 85, {"app/auth": 95})[1]
    assert auth == GateResult("app/auth", 90.0, 95.0)
    assert not auth.ok


def test_missing_package_is_an_error() -> None:
    with pytest.raises(ValueError, match="app/nope"):
        package_percent(_report()["files"], "app/nope")


def test_windows_paths_are_normalized() -> None:
    assert package_percent(_report()["files"], "app/dwh/") == 100.0


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(_report()), encoding="utf-8")
    assert main([str(path), "--total", "85", "--package", "app/core=95"]) == 0
    assert main([str(path), "--total", "85", "--package", "app/auth=95"]) == 1
    assert main([str(path), "--total", "85", "--package", "app/nope=95"]) == 2
    out = capsys.readouterr().out
    assert "FAIL app/auth" in out
    assert "XATO" in out
