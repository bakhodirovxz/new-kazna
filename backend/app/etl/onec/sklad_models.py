"""1C `hs/sklad/materials` javobi (S3 spec 3.3). Joriy shakl (eski dashboard): data[] —
accountCode, accountName, isTotal, openingSum, closingSum (so'm). Ixtiyoriy maydonlar —
1C dasturchilaridan so'ralgan kengaytma (docs/integration/1c-sorov-s3.md, G1–G5); snake_case va
camelCase ikkalasi qabul qilinadi. {"success": false, "code", "error"} — xizmat xatosi.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.etl.onec.client import OneCError
from app.etl.onec.models import parse


def _alias(*names: str) -> AliasChoices:
    return AliasChoices(*names)


class MaterialRow(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, coerce_numbers_to_str=True)
    account_code: str = Field(validation_alias=_alias("accountCode", "account_code"),
                              pattern=r"^\d{2,8}$")
    account_name: str = Field(validation_alias=_alias("accountName", "account_name"),
                              min_length=1, max_length=300)
    is_total: bool = Field(False, validation_alias=_alias("isTotal", "is_total"))
    opening: Decimal = Field(Decimal(0),
                             validation_alias=_alias("openingSum", "opening_sum", "opening"))
    closing: Decimal = Field(validation_alias=_alias("closingSum", "closing_sum", "closing"))
    nomenclature_code: str | None = Field(
        None, validation_alias=_alias("nomenclature_code", "nomenclatureCode"), max_length=100)
    nomenclature_name: str | None = Field(
        None, validation_alias=_alias("nomenclature_name", "nomenclatureName"), max_length=300)
    unit: str | None = Field(None, validation_alias=_alias("unit"), max_length=16)
    warehouse_name: str | None = Field(
        None, validation_alias=_alias("warehouse_name", "warehouseName"), max_length=100)
    closing_qty: Decimal | None = Field(None,
                                        validation_alias=_alias("closing_qty", "closingQty"))
    min_qty: Decimal | None = Field(None, validation_alias=_alias("min_qty", "minQty"))
    last_move_date: date | None = Field(
        None, validation_alias=_alias("last_move_date", "lastMoveDate"))
    debit_sum: Decimal | None = Field(None, validation_alias=_alias("debit_sum", "debitSum"))
    credit_sum: Decimal | None = Field(None, validation_alias=_alias("credit_sum", "creditSum"))


class MaterialsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    data: list[MaterialRow]


def parse_materials(data: Any) -> MaterialsResponse:
    if isinstance(data, dict) and data.get("success") is False:
        code = str(data.get("code", ""))[:40]
        error = str(data.get("error", ""))[:200]
        raise OneCError(f"1С /materials: ошибка сервиса {code} {error}".strip())
    return parse(MaterialsResponse, data, "/materials")
