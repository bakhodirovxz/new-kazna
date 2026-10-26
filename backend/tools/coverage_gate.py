"""Qamrov darvozasi (spec 9): umumiy va paket bo'yicha minimal foizlar.

Ishlatish:
    pytest --cov=app --cov-report=json:/tmp/coverage.json
    python tools/coverage_gate.py /tmp/coverage.json --total 85 --package app/core=95
Chiqish kodi: 0 — hamma chegara bajarildi, 1 — chegara buzildi, 2 — ma'lumot xatosi.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class GateResult:
    name: str
    percent: float
    minimum: float

    @property
    def ok(self) -> bool:
        return self.percent + 1e-9 >= self.minimum


def package_percent(files: dict[str, Any], prefix: str) -> float:
    """`prefix` ostidagi fayllar bo'yicha qatorlar qamrovi (Windows yo'llari ham)."""
    norm_prefix = prefix.replace("\\", "/").rstrip("/") + "/"
    covered = 0
    total = 0
    for path, data in files.items():
        if path.replace("\\", "/").startswith(norm_prefix):
            covered += int(data["summary"]["covered_lines"])
            total += int(data["summary"]["num_statements"])
    if total == 0:
        raise ValueError(f"{prefix}: qamrov hisobotida bu paketdan fayl yo'q")
    return 100.0 * covered / total


def evaluate(
    report: dict[str, Any], total_min: float, packages: dict[str, float]
) -> list[GateResult]:
    totals = report["totals"]
    statements = int(totals["num_statements"])
    total_pct = 100.0 * int(totals["covered_lines"]) / statements if statements else 0.0
    results = [GateResult("TOTAL", total_pct, total_min)]
    for prefix, minimum in packages.items():
        results.append(GateResult(prefix, package_percent(report["files"], prefix), minimum))
    return results


def _package(value: str) -> tuple[str, float]:
    prefix, _, minimum = value.partition("=")
    if not prefix or not minimum:
        raise argparse.ArgumentTypeError("format: <yo'l>=<foiz>, masalan app/core=95")
    return prefix, float(minimum)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coverage_gate")
    parser.add_argument("report", type=Path)
    parser.add_argument("--total", type=float, required=True)
    parser.add_argument("--package", type=_package, action="append", default=[])
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    try:
        results = evaluate(report, args.total, dict(args.package))
    except ValueError as exc:
        sys.stdout.write(f"XATO: {exc}\n")
        return 2
    for r in results:
        status = "OK  " if r.ok else "FAIL"
        sys.stdout.write(f"{status} {r.name} {r.percent:.2f}% (min {r.minimum:.0f}%)\n")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
