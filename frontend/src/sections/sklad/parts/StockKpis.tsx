import type { StockKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate, formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

/** Prototip `kpisWh`: стоимость, оборачиваемость, ниже минимума, неликвиды, приход, расход. */
export function StockKpis({ kpis }: { kpis: StockKpisOut }) {
  const value = moneyParts(kpis.value);
  const inflow = moneyParts(kpis.inflow);
  const outflow = moneyParts(kpis.outflow);
  const noSource = t('sklad.kpi.noSource');
  return (
    <KpiGrid>
      <KpiTile icon="box" label={t('sklad.kpi.value')} value={value.value} unit={value.unit} delta={t('sklad.kpi.valueNote', { date: formatDate(kpis.as_of) })} hint={formula('stockValue')} />
      <KpiTile
        icon="clock"
        label={t('sklad.kpi.turnover')}
        value={kpis.turnover_days === null ? t('dash.noValue') : formatNumber(kpis.turnover_days, 0)}
        unit={kpis.turnover_days === null ? undefined : t('unit.days')}
        delta={t('sklad.kpi.turnoverNote')}
        hint={formula('turnover')}
      />
      <KpiTile
        icon="alert"
        label={t('sklad.kpi.below')}
        value={kpis.has_minimum ? String(kpis.below_min) : t('dash.noValue')}
        negative={kpis.has_minimum && kpis.below_min > 5}
        delta={kpis.has_minimum ? t('sklad.kpi.belowNote', { count: kpis.positions }) : noSource}
        hint={formula('belowMin')}
      />
      <KpiTile
        icon="pct"
        label={t('sklad.kpi.illiquid')}
        value={kpis.has_age ? formatPct(kpis.idle_share, 1) : t('dash.noValue')}
        negative={kpis.idle_share !== null && kpis.idle_share > 0.2}
        delta={kpis.has_age ? t('sklad.kpi.illiquidNote', { amount: formatMoney(kpis.idle_value) }) : noSource}
        hint={formula('illiquid')}
      />
      <KpiTile icon="in" label={t('sklad.kpi.inflow')} value={inflow.value} unit={inflow.unit} delta={t('sklad.kpi.period')} hint={formula('stockFlow')} />
      <KpiTile icon="out" label={t('sklad.kpi.outflow')} value={outflow.value} unit={outflow.unit} delta={t('sklad.kpi.period')} hint={formula('stockFlow')} />
    </KpiGrid>
  );
}
