"""Bank fayl formatlari adapterlari. Yangi bank formati = yangi adapter sinfi + shu lug'atga
bitta qator + `ADAPTER_NAMES` (registry) ga nom; `banks.formats` sozlamasi bankka adapter beradi."""

from __future__ import annotations

from typing import Protocol

from app.etl.banks.canonical import CanonicalCsvAdapter
from app.etl.banks.models import ParsedFile


class StatementAdapter(Protocol):
    name: str

    def parse(self, data: bytes, name: str) -> ParsedFile: ...


ADAPTERS: dict[str, StatementAdapter] = {"canonical": CanonicalCsvAdapter()}
