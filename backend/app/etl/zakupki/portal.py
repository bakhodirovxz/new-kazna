"""Xarid portali adapteri interfeysi (S4 spec 3.1). xarid.uzex.uz / davlat xaridlari portali
formati mijoz bilan kelishilmagan (TZ 8: «API портала или реестровая выгрузка», 2-bosqich),
shuning uchun protokol + «не настроен» stub'i; kanonik qatorlarga xaritalash —
ProcurementConnector'da (adapter faqat PortalLot beradi).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.core.config import ConfigError
from app.etl.keys import normalize_name
from app.etl.types import HealthResult, Window
from app.etl.zakupki.codes import CANCELLED, DONE, IN_WORK

PORTAL_MESSAGE = ("Портал закупок не настроен: формат выгрузки xarid.uzex.uz не согласован — "
                  "загружайте лоты CSV-файлом (docs/integration/zakupki-format.md)")


@dataclass(frozen=True, slots=True)
class PortalLot:
    lot_no: str
    customer_inn: str
    method: str
    status: str
    announce_date: date
    contract_date: date | None
    start_price_uzs: Decimal
    contract_price_uzs: Decimal | None
    supplier_inn: str | None
    supplier_name: str | None
    subject: str


class ProcurementPortal(Protocol):
    name: str

    def healthcheck(self) -> HealthResult: ...

    def lots(self, window: Window) -> Iterator[PortalLot]: ...


class PortalNotConfigured(ConfigError):  # noqa: N818
    """Portal formati hali kelishilmagan (spec 12, 1-savol)."""


class XaridPortal:
    name = "xarid"

    def __init__(self) -> None:
        raise PortalNotConfigured(PORTAL_MESSAGE)

    def healthcheck(self) -> HealthResult:
        raise PortalNotConfigured(PORTAL_MESSAGE)

    def lots(self, window: Window) -> Iterator[PortalLot]:
        raise PortalNotConfigured(PORTAL_MESSAGE)


def _key(name: str) -> str:
    return normalize_name(name).replace("ё", "е")


_METHODS = {_key(k): v for k, v in {
    "Электронный магазин": "eshop", "Elektron do'kon": "eshop",
    "Электронный конкурс": "contest", "Конкурс": "contest", "Tanlov": "contest",
    "Тендер": "tender", "Tender": "tender",
    "Биржевые торги": "exchange", "Биржа": "exchange", "Birja savdolari": "exchange",
    "Прямой договор": "direct", "To'g'ridan-to'g'ri shartnoma": "direct",
}.items()}
_STATUSES = {_key(k): v for k, v in {
    "Объявлен": IN_WORK[0], "Опубликован": IN_WORK[0], "На оценке": IN_WORK[1],
    "Рассмотрение предложений": IN_WORK[1], "Договор заключён": DONE,
    "Заключен договор": DONE, "Отменён": CANCELLED, "Аннулирован": CANCELLED,
}.items()}


def method_code(name: str) -> str | None:
    return _METHODS.get(_key(name))


def status_code(name: str) -> str | None:
    return _STATUSES.get(_key(name))
