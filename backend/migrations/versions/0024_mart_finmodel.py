"""S5: финмодель — 4 ssenariy × 7 yil, build bo'yicha (kirish bazasi har qatorda)

Revision ID: 0024
Revises: 0023a
Create Date: 2026-09-25

Faqat kompaniya darajasi: branch_id = 0 — RLS bo'yicha faqat scope_all foydalanuvchilar ko'radi.
"""

from alembic import op

revision = "0024"
down_revision = "0023a"  # prod head 0023a (reja 0020 -> 0024, integrator tomonidan qayta zanjirlandi)
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
COLUMNS = (
    "branch_id, month_id, scenario, year, capacity_mw, generation, supply, tariff, revenue, opex, "
    "tax, ebitda, margin, capex_plan, capex, principal, interest, debt_service, net_flow, "
    "balance, dscr, covenant_breach, unit_cost, as_of_id, base_capacity_mw, opex_base, "
    "opex_months, opening_cash, missing_fx, assumptions_at, covenant"
)

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_finmodel_year (
      build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE,
      branch_id integer NOT NULL CHECK (branch_id = 0),
      month_id integer NOT NULL,
      scenario varchar(8) NOT NULL CHECK (scenario IN ('base', 'water', 'tariff', 'fx')),
      year smallint NOT NULL CHECK (year BETWEEN 2020 AND 2100),
      capacity_mw numeric(12,2) NOT NULL,
      generation numeric(20,3) NOT NULL,
      supply numeric(20,3) NOT NULL,
      tariff numeric(14,2) NOT NULL,
      revenue {MONEY},
      opex {MONEY},
      tax {MONEY},
      ebitda {MONEY},
      margin numeric(20,6),
      capex_plan {MONEY},
      capex {MONEY},
      principal {MONEY},
      interest {MONEY},
      debt_service {MONEY},
      net_flow {MONEY},
      balance {MONEY},
      dscr numeric(20,4),
      covenant_breach boolean NOT NULL,
      unit_cost numeric(20,2),
      as_of_id integer NOT NULL,
      base_capacity_mw numeric(12,2) NOT NULL,
      opex_base {MONEY},
      opex_months smallint NOT NULL,
      opening_cash {MONEY},
      missing_fx varchar(8)[] NOT NULL DEFAULT '{{}}',
      assumptions_at timestamptz,
      covenant numeric(8,4) NOT NULL,
      PRIMARY KEY (build_id, branch_id, month_id, scenario, year)
    )
    """,
    f"""
    CREATE VIEW pub.agg_finmodel_year WITH (security_invoker = true) AS
    SELECT {COLUMNS}
    FROM mart.agg_finmodel_year a WHERE a.build_id = {ACTIVE}
    """,
    "ALTER TABLE mart.agg_finmodel_year ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE mart.agg_finmodel_year FORCE ROW LEVEL SECURITY",
    "CREATE POLICY branch_scope ON mart.agg_finmodel_year USING (core.rls_branch_ok(branch_id)) "
    "WITH CHECK (core.rls_branch_ok(branch_id))",
    "GRANT SELECT ON mart.agg_finmodel_year TO ugk_app",
    "GRANT SELECT, INSERT, DELETE ON mart.agg_finmodel_year TO ugk_etl",
    "GRANT SELECT ON pub.agg_finmodel_year TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP VIEW pub.agg_finmodel_year")
    op.execute("DROP TABLE mart.agg_finmodel_year")
