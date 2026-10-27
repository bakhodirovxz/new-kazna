import type { ZakKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

const PLAN_LOW = 0.6; // TZ 4 qoidasi «План закупок освоено < 60%»
const DIRECT_HIGH = 0.25; // TZ 4 qoidasi «Доля прямых договоров > 25%»

/** Prototip `kpisZak`: договоры, план, экономия, лоты в работе, просроченные, прямые договоры. */
export function ZakKpis({ kpis }: { kpis: ZakKpisOut }) {
  const contracted = moneyParts(kpis.contracted);
  const savings = moneyParts(kpis.savings);
  return (
    <KpiGrid>
      <KpiTile icon="cart" label={t('zak.kpi.contracted')} value={contracted.value} unit={contracted.unit} delta={t('zak.kpi.contractedNote', { count: kpis.contracts })} hint={formula('contracted')} />
      <KpiTile
        icon="pct"
        label={t('zak.kpi.plan')}
        value={<span className={kpis.plan_execution !== null && kpis.plan_execution < PLAN_LOW ? 'neg' : undefined}>{formatPct(kpis.plan_execution, 1)}</span>}
        delta={t('zak.kpi.planNote', { ytd: formatMoney(kpis.ytd), plan: formatMoney(kpis.plan) })}
        hint={formula('planExec')}
      />
      <KpiTile icon="coins" label={t('zak.kpi.savings')} value={savings.value} unit={savings.unit} delta={t('zak.kpi.savingsNote', { share: formatPct(kpis.savings_share, 1) })} hint={formula('savings')} />
      <KpiTile icon="clock" label={t('zak.kpi.inWork')} value={formatNumber(kpis.in_work)} delta={t('zak.kpi.inWorkNote', { amount: formatMoney(kpis.in_work_start) })} hint={formula('lotsInWork')} />
      <KpiTile
        icon="alert"
        label={t('zak.kpi.overdue')}
        value={<span className={kpis.overdue > 0 ? 'neg' : undefined}>{formatNumber(kpis.overdue)}</span>}
        delta={kpis.overdue > 0 ? t('zak.kpi.overdueNote') : t('zak.kpi.overdueNone')}
        hint={formula('lotsOverdue')}
      />
      <KpiTile
        icon="doc"
        label={t('zak.kpi.direct')}
        value={<span className={kpis.direct_share !== null && kpis.direct_share > DIRECT_HIGH ? 'neg' : undefined}>{formatPct(kpis.direct_share, 1)}</span>}
        delta={t('zak.kpi.directNote', { amount: formatMoney(kpis.direct) })}
        hint={formula('directShare')}
      />
    </KpiGrid>
  );
}
