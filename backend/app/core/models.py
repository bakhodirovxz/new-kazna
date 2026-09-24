"""ORM asosi: barcha jadvallar `core` sxemasida, vaqt ustunlari timezone-aware."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(schema="core")
    type_annotation_map: ClassVar = {datetime: DateTime(timezone=True)}
