"""DirectBank (1С) — interfeys va stub (S2 spec 3.2). Mijoz 1C konfiguratsiyasi, ochiladigan
ma'lumot va texnik hisob haqida javob berguncha ulanish yo'q; javobdan keyin DirectBankClient
amalga oshiriladi va BankMapper (fayl yo'li bilan umumiy) orqali staging'ga yoziladi."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.core.config import ConfigError
from app.etl.banks.models import ParsedFile

DIRECTBANK_MESSAGE = ("DirectBank (1С) не настроен: ожидается ответ заказчика по формату и "
                      "доступу; выписки загружаются файлами (docs/integration/banks-connector.md)")


class DirectBankNotConfiguredError(ConfigError):
    """DirectBank ulanishi sozlanmagan."""


class DirectBankClient(Protocol):
    def statements(self, account_codes: Sequence[str], day: date) -> ParsedFile: ...

    def order_statuses(self, account_codes: Sequence[str], day: date) -> ParsedFile: ...


class OneCDirectBankClient:
    """1С DirectBank mijozi — hozircha yaratib bo'lmaydi."""

    def __init__(self) -> None:
        raise DirectBankNotConfiguredError(DIRECTBANK_MESSAGE)

    def statements(self, account_codes: Sequence[str], day: date) -> ParsedFile:
        raise DirectBankNotConfiguredError(DIRECTBANK_MESSAGE)

    def order_statuses(self, account_codes: Sequence[str], day: date) -> ParsedFile:
        raise DirectBankNotConfiguredError(DIRECTBANK_MESSAGE)
