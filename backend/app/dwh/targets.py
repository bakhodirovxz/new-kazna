"""Staging maqsadlari reyestri: har dwh jadvali uchun ustunlar, idempotentlik kaliti,
o'lcham kodlarini id'ga aylantirish (lookup), SCD-2 va shifrlanadigan maydonlar.

DIQQAT: o'lchov `code` ustuni OCHIQ matn sifatida saqlanadi, shifrlash AAD'iga kiradi
("{schema}.{table}.{column}:{pk}") va topilmagan lookup xatosida `etl_error.message`ga
yoziladi — shuning uchun `code` hech qachon INN, hisob raqami yoki boshqa sezgir qiymat
bo'lmasligi shart (ular faqat `*_enc`/`*_bidx` ustunlarida).

Barcha SQL identifikatorlari shu fayldan olinadi (whitelist) — tashqi kiritishdan emas.
Keyingi rejalar yangi fakt qo'shganda faqat shu yerga Target qo'shadi.

Faktlarning tabiiy kaliti — `(src_system, doc_type, src_id)` (partitsiyalangan jadvallarda
PostgreSQL talabiga ko'ra `date_id` ham qo'shiladi, spec 4.6/Global Constraints #3): bitta
hujjat (`src_id`) sana bo'yicha BIR MARTA uchraydi — snapshot faktlar (masalan,
`fact_balance`, `fact_stock`) uchun `src_id` shu sababli sana kesimida emas, HUJJAT
(o'lchov nuqtasi) kesimida noyob bo'lishi kerak. Hujjat sanasi o'zgarsa (`app/etl/merge.py`
`_moved_sql`), yangi yuklash o'sha `(doc_type, src_id)` bo'yicha eski partitsiyadagi
nusxani topib o'chiradi — shuning uchun bitta partiyada bir xil `(doc_type, src_id)` ikki xil
`date_id` bilan kelsa, oxirgisi (`seq` bo'yicha) g'olib chiqadi (spec 5.2, fix r1 I2).

Lookup kalit nomlanishi — `Lookup.key`: ustun nomidan `_id` olib tashlanadi va `_code`
qo'shiladi (masalan, `branch_id` → `branch_code`, `item_id` → `item_code`): staging payload'i
o'lchov SURROGAT id'sini emas, TABIIY kodni beradi — id'ga aylantirish shu modulda,
`app/etl/merge.py`dagi LEFT JOIN orqali bajariladi (fix r1 M5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.crypto import Purpose

# Tizim "Прочие" statyalari (0005 migratsiyasida seed qilingan).
OTHER_IN_ITEM = "PKM54-I06"
OTHER_OUT_ITEM = "PKM54-O09"
_ITEM_BY_DIRECTION = (
    f"CASE WHEN s.payload->>'direction' = 'in' THEN '{OTHER_IN_ITEM}' "
    f"ELSE '{OTHER_OUT_ITEM}' END"
)
_ITEM_OUT = f"'{OTHER_OUT_ITEM}'"
# fact_payment_plan ichida sanali to'lov jadvali (kalendar) oylik rejadan shu doc_type
# bilan ajraladi.
SCHEDULE_DOC_TYPE = "payment_schedule"


@dataclass(frozen=True, slots=True)
class Lookup:
    column: str  # dwh ustuni va o'lcham PK nomi, masalan "item_id"
    dim: str  # "dim_item"
    nullable: bool = False
    fallback_sql: str | None = None  # topilmasa ishlatiladigan KOD ifodasi (statya → «Прочие»)

    @property
    def key(self) -> str:
        return self.column.removesuffix("_id") + "_code"

    @property
    def error_code(self) -> str:
        if self.column == "branch_id":
            return "missing_branch"
        return "missing_item" if self.fallback_sql else "missing_dim"

    @property
    def severity(self) -> str:
        return "warning" if self.fallback_sql else "error"


@dataclass(frozen=True, slots=True)
class Scd:
    table: str
    key: str
    column: str


@dataclass(frozen=True, slots=True)
class Sensitive:
    field: str  # manbadagi ochiq maydon
    enc_column: str
    bidx_column: str
    purpose: Purpose
    index_label: str


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    kind: Literal["dim", "fact"]
    columns: tuple[str, ...]  # payload'dan to'g'ridan-to'g'ri olinadigan ustunlar
    conflict: tuple[str, ...]
    lookups: tuple[Lookup, ...] = ()
    partition: Literal["month", "year"] | None = None
    windowed: bool = False  # oyna ichida to'liq almashtiriladi
    scd: Scd | None = None
    sensitive: tuple[Sensitive, ...] = ()
    # Manba kelajak sanali qatorlarni ham to'liq beradi (reja, jadval): to'liq almashtirishda
    # oynadan keyingi eski qatorlar ham o'chiriladi.
    forward: bool = False

    @property
    def allowed_keys(self) -> frozenset[str]:
        """`DbStagingSink.add()` whitelist (fix r1, I1): staging payload shu to'plamdan
        tashqari kalit qabul qilmaydi. `enc_column`/`bidx_column` bu yerda YO'Q — ular
        faqat `app.etl.staging.protect()` tomonidan hosil qilinadi, chaqiruvchi ularni
        to'g'ridan-to'g'ri bera olmaydi (shifrlangan qiymatni "soxtalashtirish"dan himoya)."""
        enc_bidx = {c for s in self.sensitive for c in (s.enc_column, s.bidx_column)}
        return frozenset(
            (set(self.columns) - enc_bidx)
            | {lk.key for lk in self.lookups}
            | {s.field for s in self.sensitive}
        )


BRANCH = Lookup("branch_id", "dim_branch")
_FACT_TECH = ("doc_type", "src_id", "date_id")


def _dim(name: str, columns: tuple[str, ...], **kw: object) -> Target:
    return Target(name, "dim", columns, ("code",), **kw)  # type: ignore[arg-type]


def _fact(name: str, measures: tuple[str, ...], lookups: tuple[Lookup, ...],
          partition: Literal["month", "year"] | None = None, *, forward: bool = False) -> Target:
    conflict = ("src_system", "doc_type", "src_id") + (("date_id",) if partition else ())
    return Target(name, "fact", _FACT_TECH + measures, conflict, lookups, partition,
                  windowed=True, forward=forward)


_ALL: tuple[Target, ...] = (
    _dim("dim_branch",
         ("code", "name", "short_name", "inn", "kind", "capacity_mw", "lat", "lon", "sort_order"),
         scd=Scd("dim_branch_version", "branch_id", "capacity_mw")),
    _dim("dim_item", ("code", "name", "activity", "direction", "sort_order")),
    _dim("dim_counterparty", ("code", "name", "kind", "inn_enc", "inn_bidx"),
         sensitive=(Sensitive("inn", "inn_enc", "inn_bidx", Purpose.PII, "inn"),)),
    _dim("dim_bank", ("code", "bank_name", "account_enc", "account_bidx", "currency"),
         sensitive=(Sensitive("account_number", "account_enc", "account_bidx", Purpose.BANK,
                              "account"),)),
    _dim("dim_nomenclature", ("code", "name", "category", "unit", "enbt_code")),
    _dim("dim_source", ("code", "name", "kind")),
    _dim("dim_object",
         ("code", "name", "program_code", "work_type", "commissioning_year", "total_cost"),
         lookups=(Lookup("source_id", "dim_source", nullable=True),)),
    _dim("dim_contract", ("code", "number", "contract_date", "amount", "end_date", "kind"),
         lookups=(BRANCH, Lookup("cp_id", "dim_counterparty"),
                  Lookup("object_id", "dim_object", nullable=True))),
    _dim("dim_loan",
         ("code", "creditor", "project", "currency", "rate", "grace_until", "maturity",
          "amount_uzs"),
         lookups=(BRANCH,), scd=Scd("dim_loan_version", "loan_id", "rate")),
    _dim("dim_position", ("code", "category", "department")),
    Target("fx_rate", "fact", ("currency", "date_id", "rate"), ("currency", "date_id")),
    _fact("fact_cashflow", ("direction", "amount", "gl_account"),
          (BRANCH, Lookup("item_id", "dim_item", fallback_sql=_ITEM_BY_DIRECTION),
           Lookup("cp_id", "dim_counterparty", nullable=True),
           Lookup("contract_id", "dim_contract", nullable=True),
           Lookup("bank_id", "dim_bank", nullable=True)), "month"),
    _fact("fact_balance", ("balance",), (BRANCH, Lookup("bank_id", "dim_bank")), "year"),
    _fact("fact_payment_plan", ("amount",),
          (BRANCH, Lookup("item_id", "dim_item", fallback_sql=_ITEM_OUT)), forward=True),
    _fact("fact_payment_order", ("amount", "status", "status_date_id"),
          (BRANCH, Lookup("item_id", "dim_item", fallback_sql=_ITEM_OUT),
           Lookup("cp_id", "dim_counterparty", nullable=True),
           Lookup("bank_id", "dim_bank", nullable=True)), "month"),
    _fact("fact_debt", ("receivable", "payable", "overdue", "overdue_days"),
          (BRANCH, Lookup("contract_id", "dim_contract"),
           Lookup("cp_id", "dim_counterparty", nullable=True)), "year"),
    _fact("fact_generation", ("generation", "own_needs", "supply", "plan", "work_hours"),
          (BRANCH,), "year"),
    _fact("fact_energy_sales", ("accrued", "paid", "volume"),
          (BRANCH, Lookup("cp_id", "dim_counterparty"))),
    _fact("fact_procurement",
          ("lot_no", "method", "status", "start_price", "contract_price", "procedure_days"),
          (BRANCH, Lookup("nom_id", "dim_nomenclature", nullable=True),
           Lookup("cp_id", "dim_counterparty", nullable=True))),
    _fact("fact_stock", ("warehouse", "qty", "value", "min_qty", "last_move_date_id"),
          (BRANCH, Lookup("nom_id", "dim_nomenclature")), "year"),
    _fact("fact_stock_move", ("direction", "qty", "value"),
          (BRANCH, Lookup("nom_id", "dim_nomenclature")), "year"),
    _fact("fact_investment", ("plan", "fact", "physical_pct", "advance", "advance_date_id"),
          (BRANCH, Lookup("object_id", "dim_object"),
           Lookup("source_id", "dim_source", nullable=True))),
    _fact("fact_loan_schedule", ("principal", "interest", "balance"),
          (BRANCH, Lookup("loan_id", "dim_loan")), forward=True),
    _fact("fact_hr",
          ("headcount_plan", "headcount_fact", "payroll", "hired", "fired", "overtime_hours"),
          (BRANCH, Lookup("pos_id", "dim_position"))),
    _fact("fact_target_funds", ("allocated", "used"),
          (BRANCH, Lookup("source_id", "dim_source"),
           Lookup("object_id", "dim_object", nullable=True))),
)

TARGETS: dict[str, Target] = {t.name: t for t in _ALL}
DIM_TARGETS: tuple[str, ...] = tuple(t.name for t in _ALL if t.kind == "dim")
FACT_TARGETS: tuple[str, ...] = tuple(t.name for t in _ALL if t.kind == "fact")
