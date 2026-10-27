"""Manba identifikatorlari uchun umumiy nomlar: `stable_code`/`to_mln` — S1 1C konnektorining
yagona realizatsiyasi; `normalize_name` — `hr.orgs` / xarid solishtirish normallashtirishi."""

from __future__ import annotations

from app.core.setting_types import normalize_org as normalize_name
from app.etl.onec.connector import stable_code, to_mln

__all__ = ["normalize_name", "stable_code", "to_mln"]
