import type { ProdKpisOut, ReportPeriodOut } from '../../../api/types';
import { formatKwh, kwhParts } from '../../../dash/energy';
import { formula } from '../../../dash/formulas';
import { formatDelta, formatMoney, formatPct, yoyRatio } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

const LOW_PLAN = 0.95;
const LOW_PAYMENT = 0.85;

/** Prototip `kpisProd`: выработка (к прошлому году), план, мощность, КИУМ, отпуск, уровень оплаты. */
export function ProdKpis({ kpis, period }: { kpis: ProdKpisOut; period: ReportPeriodOut }) {
  const generation = kwhParts(kpis.generation);
  const supply = kwhParts(kpis.supply);
  const ratio = yoyRatio(kpis.generation, kpis.generation_prev);
  const year = Number(period.date_from.slice(0, 4)) - 1;
  const yoy = ratio === null ? null : t('dash.yoy', { year, delta: formatDelta(ratio) });
  return (
    <KpiGrid>
      <KpiTile
        icon="bolt"
        label={t('proizv.kpi.generation')}
        value={generation.value}
        unit={generation.unit}
        delta={yoy ? `${t('proizv.kpi.period')} · ${yoy}` : t('proizv.kpi.period')}
        deltaDown={ratio !== null && ratio < 0}
        hint={`${formula('generation')}. ${formula('yoy')}`}
      />
      <KpiTile
        icon="pct"
        label={t('proizv.kpi.execution')}
        value={formatPct(kpis.execution, 1)}
        negative={kpis.execution !== null && kpis.execution < LOW_PLAN}
        delta={t('proizv.kpi.executionNote', { plan: formatKwh(kpis.plan) })}
        hint={formula('genPlan')}
      />
      <KpiTile
        icon="factory"
        label={t('proizv.kpi.capacity')}
        value={formatNumber(kpis.capacity_mw ?? 0)}
        unit={t('unit.mw')}
        delta={t('proizv.kpi.capacityNote', { count: kpis.stations })}
        hint={formula('capacity')}
      />
      <KpiTile icon="clock" label={t('proizv.kpi.kium')} value={formatPct(kpis.kium, 1)} delta={t('proizv.kpi.kiumNote')} hint={formula('kium')} />
      <KpiTile
        icon="plug"
        label={t('proizv.kpi.supply')}
        value={supply.value}
        unit={supply.unit}
        delta={t('proizv.kpi.supplyNote', { share: formatPct(kpis.own_share, 1) })}
        hint={`${formula('supply')}. ${formula('ownNeeds')}`}
      />
      <KpiTile
        icon="coins"
        label={t('proizv.kpi.payment')}
        value={formatPct(kpis.payment_level, 1)}
        negative={kpis.payment_level !== null && kpis.payment_level < LOW_PAYMENT}
        delta={t('proizv.kpi.paymentNote', { paid: formatMoney(kpis.paid), accrued: formatMoney(kpis.accrued) })}
        hint={formula('paymentLevel')}
      />
    </KpiGrid>
  );
}
