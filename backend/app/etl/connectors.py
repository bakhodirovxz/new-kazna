"""Manba nomi → konnektor. 1C, DirectBank va boshqalar keyingi rejalarda qo'shiladi."""

from __future__ import annotations

from pathlib import Path

from app.core.config import ConfigError, Settings, get_settings
from app.etl.file_connector import FileConnector
from app.etl.synthetic import SyntheticConnector
from app.etl.types import SourceConnector

KNOWN_SOURCES = ("synthetic", "file")


def make_connector(source: str, settings: Settings | None = None) -> SourceConnector:
    settings = settings or get_settings()
    if source == "synthetic":
        if settings.env == "prod":
            raise ConfigError("SyntheticConnector prod muhitida taqiqlangan")
        return SyntheticConnector(seed=settings.synthetic_seed)
    if source == "file":
        return FileConnector(Path(settings.etl_file_dir))
    raise ValueError(f"noma'lum manba: {source}")
