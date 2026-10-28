import type { FinBaseOut, FinSummaryOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

/** Prototip `kpisFin`: мощность 2032, выручка 2032, рентабельность, инвестиции, мин. DSCR, накопленный поток. */
export function FinKpis({ summary, base }: { summary: FinSummaryOut; base: FinBaseOut }) {
  const revenue = moneyParts(summary.revenue_last);
  const capex = moneyParts(summary.capex_total);
  const cum = moneyParts(summary.cum_flow);
  const lowDscr = summary.dscr_min !== null && summary.dscr_min < base.covenant;
  return (
    <KpiGrid>
      <KpiTile icon="factory" label={t('fm.kpi.capacity')} value={formatNumber(summary.capacity_last, 0)} unit={t('fm.unit.mw')} delta={t('fm.kpi.capacityNote', { mw: formatNumber(summary.capacity_added, 0) })} hint={formula('finCapacity')} />
      <KpiTile icon="coins" label={t('fm.kpi.revenue')} value={revenue.value} unit={revenue.unit} delta={t('fm.kpi.revenueNote', { amount: formatMoney(summary.revenue_first) })} hint={formula('finRevenue')} />
      <KpiTile icon="pct" label={t('fm.kpi.margin')} value={formatPct(summary.margin_avg, 1)} delta={t('fm.kpi.marginNote')} hint={formula('finMargin')} />
      <KpiTile icon="target" label={t('fm.kpi.capex')} value={capex.value} unit={capex.unit} delta={t('fm.kpi.capexNote')} hint={formula('finCapex')} />
      <KpiTile
        icon="bank"
        label={t('fm.kpi.dscr')}
        value={summary.dscr_min === null ? t('dash.noValue') : formatNumber(summary.dscr_min, 2)}
        negative={lowDscr}
        delta={summary.dscr_min_year === null ? t('fm.kpi.dscrNone') : t('fm.kpi.dscrNote', { year: summary.dscr_min_year, covenant: formatNumber(base.covenant, 2) })}
        hint={formula('dscr')}
      />
      <KpiTile
        icon="net"
        label={t('fm.kpi.cum')}
        value={cum.value}
        unit={cum.unit}
        negative={summary.cum_flow < 0}
        delta={summary.negative_years > 0 ? t('fm.kpi.cumNeg', { count: summary.negative_years }) : t('fm.kpi.cumOk')}
        hint={formula('finCumFlow')}
      />
    </KpiGrid>
  );
}
