"""Strukturali JSON loglar; sezgir kalitlar avtomatik maskalanadi (spec 3.7)."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

MASK = "***"
_SENSITIVE_TOKENS = frozenset(
    {
        "password", "passwd", "pwd", "token", "secret", "cookie", "authorization",
        "totp", "otp", "kek", "pepper", "csrf", "inn", "account",
    }
)
_SENSITIVE_KEYS = frozenset({"code", "mfa_code", "backup_code"})
_SPLIT = re.compile(r"[_\-.\s]+")
_RESERVED = frozenset({"event", "level", "timestamp", "logger"})


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return lowered in _SENSITIVE_KEYS or any(t in _SENSITIVE_TOKENS for t in _SPLIT.split(lowered))


def mask(value: Any, key: str | None = None) -> Any:
    if key is not None and _is_sensitive(key):
        return MASK
    if isinstance(value, dict):
        return {str(k): mask(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [mask(v) for v in value]
    return value


def _mask_processor(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> dict[str, Any]:
    return {k: (v if k in _RESERVED else mask(v, k)) for k, v in event_dict.items()}


def configure_logging(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _mask_processor,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
