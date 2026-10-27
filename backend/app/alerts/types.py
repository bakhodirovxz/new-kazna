"""Qoida konfiguratsiyasi (core.alert_rules) va natija tiplari."""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.sections.deps import SectionQuery

_OPS: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge,
}


@dataclass(frozen=True, slots=True)
class RuleConfig:
    code: str
    title: str
    section: str
    page: str
    level: str  # critical | warning
    threshold: dict[str, Any]

    @property
    def op(self) -> str:
        return str(self.threshold.get("op", ">"))

    @property
    def value(self) -> float:
        return float(self.threshold["value"])


@dataclass(frozen=True, slots=True)
class AlertHit:
    code: str
    level: str
    title: str
    message: str
    section: str
    page: str
    value: float | None


Evaluator = Callable[["Session", "SectionQuery", RuleConfig], AlertHit | None]
REGISTRY: dict[str, Evaluator] = {}


def evaluator(code: str) -> Callable[[Evaluator], Evaluator]:
    def register(fn: Evaluator) -> Evaluator:
        if code in REGISTRY:
            raise ValueError(f"evaluator allaqachon bor: {code}")
        REGISTRY[code] = fn
        return fn

    return register


def breached(value: float, rule: RuleConfig) -> bool:
    return _OPS[rule.op](value, rule.value)


def hit(rule: RuleConfig, message: str, value: float | None) -> AlertHit:
    finite = value if value is None or value not in (float("inf"), float("-inf")) else None
    return AlertHit(rule.code, rule.level, rule.title, message, rule.section, rule.page, finite)
