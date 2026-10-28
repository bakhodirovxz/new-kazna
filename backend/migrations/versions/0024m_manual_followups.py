"""Qo'lda kiritish: hisob <-> filial aloqasi (qoldiq faktlari) va nashr xatosi holati

Revision ID: 0024m
Revises: 0023a
Create Date: 2026-10-28

`ugk_app` tanlov ro'yxati va tekshiruv uchun `dwh.fact_balance` dan faqat (branch_id, bank_id)
ni o'qiydi (FORCE RLS filial doirasini baribir cheklaydi; summa/sana/manba ko'rinmaydi).
"""

from alembic import op

revision = "0024m"
down_revision = "0023a"
branch_labels = None
depends_on = None

STATEMENTS = [
    "GRANT SELECT (branch_id, bank_id) ON dwh.fact_balance TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("REVOKE SELECT (branch_id, bank_id) ON dwh.fact_balance FROM ugk_app")
