"""ugk_etl uchun vaqtinchalik jadval huquqi

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-25

`app/etl/merge.py` har bir maqsad uchun qator darajasidagi tekshiruvni bitta o'tishda
materiallashtirish uchun `CREATE TEMP TABLE ... ON COMMIT DROP` ishlatadi (fix r1 task-5,
fix round 2, R2-4). Standart holatda ma'lumotlar bazasida `TEMPORARY` huquqi faqat egasiga
(`ugk_migrator`) berilgan — `ugk_etl`ga aniq berilishi shart, aks holda
`InsufficientPrivilege: permission denied to create temporary tables` xatosi bilan yiqiladi.
Vaqtinchalik jadvallar sessiya/tranzaksiya doirasida (`pg_temp_*` sxema) — boshqa rollarga
umuman ko'rinmaydi, shuning uchun bu RLS yoki ma'lumot izolyatsiyasiga ta'sir qilmaydi.
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "EXECUTE format('GRANT TEMPORARY ON DATABASE %I TO ugk_etl', current_database()); "
        "END $$"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM ugk_etl', current_database()); "
        "END $$"
    )
