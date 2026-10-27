"""Manbalar ustuvorligi: dwh.*_effective view'lari (qo'lda kiritilgan yozuv bo'shliqni to'ldiradi)

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-27

Qoida (spec 3.4): `src_system = 'manual'` qatori, xuddi shu DON da `manual`/`synthetic` dan boshqa
manba qatori bo'lsa yashiriladi; `synthetic` qatori xuddi shu donda `manual` qatori bo'lsa
yashiriladi. Qo'lda yozuv bo'lmasa view = jadval. Agregatlar, sifat tekshiruvi va finmodel
faqat shu view'larni o'qiydi (tests/test_code_rules.py).

`security_invoker = true`: RLS chaqiruvchi (ugk_etl, scope_all) huquqi bilan ishlaydi.
`object_stage_effective` (S4 `fact_object_stage`) bu shoxobchada yo'q -- keyingi migratsiya.
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_SCHEDULE = "payment_schedule"
# view -> (jadval, don sharti: `o` (boshqa manba qatori) va `f` (joriy qator) o'rtasida,
#          qatorlar solishtirilishi shart bo'lgan filtr: faqat shu qatorlar bosilishi mumkin)
_GRAINS: dict[str, tuple[str, str, str | None]] = {
    "balance_effective": (
        "fact_balance",
        "o.branch_id = f.branch_id AND o.bank_id = f.bank_id AND o.date_id / 100 = f.date_id / 100",
        None,
    ),
    "payment_plan_effective": (
        "fact_payment_plan",
        "o.branch_id = f.branch_id AND o.item_id = f.item_id AND ("
        f"(f.doc_type = '{_SCHEDULE}' AND o.doc_type = '{_SCHEDULE}' AND o.date_id = f.date_id) "
        f"OR (f.doc_type <> '{_SCHEDULE}' AND o.doc_type <> '{_SCHEDULE}' "
        "AND o.date_id / 100 = f.date_id / 100))",
        None,
    ),
    "debt_effective": (
        "fact_debt",
        "o.contract_id = f.contract_id AND o.date_id / 100 = f.date_id / 100",
        None,
    ),
    "target_funds_effective": (
        "fact_target_funds",
        "o.branch_id = f.branch_id AND o.source_id = f.source_id "
        "AND o.object_id IS NOT DISTINCT FROM f.object_id AND o.date_id / 100 = f.date_id / 100",
        None,
    ),
    "loan_schedule_effective": (
        "fact_loan_schedule",
        "o.loan_id = f.loan_id AND o.date_id = f.date_id",
        None,
    ),
    # faqat reja qatorlari solishtiriladi; ishlab chiqarish FAKTI shartsiz o'tadi
    "generation_effective": (
        "fact_generation",
        "o.branch_id = f.branch_id AND o.doc_type = 'generation_plan' "
        "AND o.date_id / 100 = f.date_id / 100",
        "generation_plan",
    ),
    "energy_sales_effective": (
        "fact_energy_sales",
        "o.branch_id = f.branch_id AND o.cp_id = f.cp_id AND o.date_id / 100 = f.date_id / 100",
        None,
    ),
    "investment_effective": (
        "fact_investment",
        "o.object_id = f.object_id AND o.date_id / 100 = f.date_id / 100",
        None,
    ),
    "hr_effective": (
        "fact_hr",
        "o.branch_id = f.branch_id AND o.pos_id = f.pos_id AND o.date_id / 100 = f.date_id / 100",
        None,
    ),
}


def _view_sql(view: str) -> str:
    table, same, only_doc = _GRAINS[view]
    rule = (
        f"(f.src_system <> 'manual' OR NOT EXISTS (SELECT 1 FROM dwh.{table} o "
        f"WHERE o.src_system NOT IN ('manual', 'synthetic') AND {same}))\n"
        f"  AND (f.src_system <> 'synthetic' OR NOT EXISTS (SELECT 1 FROM dwh.{table} o "
        f"WHERE o.src_system = 'manual' AND {same}))"
    )
    if only_doc:
        rule = f"(f.doc_type <> '{only_doc}' OR (\n  {rule}))"
    return (f"CREATE VIEW dwh.{view} WITH (security_invoker = true) AS\n"
            f"SELECT f.* FROM dwh.{table} f\nWHERE {rule}")


def upgrade() -> None:
    # _CASH_TOTALS lateral'i (bank, filial, sana) bo'yicha; view'dagi NOT EXISTS ham foydalanadi
    op.execute("CREATE INDEX fact_balance_grain_idx ON dwh.fact_balance (bank_id, branch_id, date_id)")
    for view in _GRAINS:
        op.execute(_view_sql(view))
        op.execute(f"GRANT SELECT ON dwh.{view} TO ugk_etl")


def downgrade() -> None:
    for view in reversed(list(_GRAINS)):
        op.execute(f"DROP VIEW dwh.{view}")
    op.execute("DROP INDEX dwh.fact_balance_grain_idx")
