"""Repo ildizi (deploy/compose.test.yml: `..:/repo:ro`) va skript modullarini yuklash."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

REPO = Path(os.environ.get("UGK_REPO", "/repo"))


def repo_path(relative: str) -> Path:
    if not REPO.is_dir():
        raise RuntimeError(
            f"Repo ildizi topilmadi: {REPO} (deploy/compose.test.yml da '..:/repo:ro' bormi?)"
        )
    return REPO / relative


def load_script(relative: str, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, repo_path(relative))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
