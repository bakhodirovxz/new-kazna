import type { CashKpisOut, ReportPeriodOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatDelta, moneyParts, yoyRatio } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';
import type { IconName } from '../../../ui/icons';

function yoy(cur: number | null, prev: number | null, year: number): { text: string; down: boolean } | null {
  if (cur === null) return null;
  const ratio = yoyRatio(cur, prev);
  return ratio === null ? null : { text: t('dash.yoy', { year, delta: formatDelta(ratio) }), down: ratio < 0 };
}

function Tile({ icon, label, value, note, change, hint }: { icon: IconName; label: string; value: number | null; note: string; change: { text: string; down: boolean } | null; hint: string }) {
  const parts = value === null ? null : moneyParts(value);
  return (
    <KpiTile
      icon={icon}
      label={label}
      value={parts ? parts.value : t('dash.noValue')}
      unit={parts?.unit}
      negative={value !== null && value < 0}
      delta={change ? `${note} · ${change.text}` : note}
      deltaDown={change?.down}
      hint={`${hint}. ${formula('yoy')}`}
    />
  );
}

/** TZ 5 «Сводка»: шесть показателей движения денежных средств с изменением к прошлому году. */
export function CashKpis({ kpis, period }: { kpis: CashKpisOut; period: ReportPeriodOut }) {
  const year = Number(period.date_from.slice(0, 4)) - 1;
  return (
    <KpiGrid>
      <Tile icon="cal" label={t('obzor.kpi.opening')} value={kpis.opening} note={t('obzor.kpi.at', { date: formatDate(period.date_from) })} change={yoy(kpis.opening, kpis.opening_prev, year)} hint={formula('opening')} />
      <Tile icon="in" label={t('obzor.kpi.inflow')} value={kpis.inflow} note={t('obzor.kpi.period')} change={yoy(kpis.inflow, kpis.inflow_prev, year)} hint={formula('inflow')} />
      <Tile icon="out" label={t('obzor.kpi.outflow')} value={kpis.outflow} note={t('obzor.kpi.period')} change={yoy(kpis.outflow, kpis.outflow_prev, year)} hint={formula('outflow')} />
      <Tile icon="net" label={t('obzor.kpi.net')} value={kpis.net} note={t('obzor.kpi.netNote')} change={yoy(kpis.net, kpis.net_prev, year)} hint={formula('net')} />
      <Tile icon="check" label={t('obzor.kpi.closing')} value={kpis.closing} note={t('obzor.kpi.closingAt', { date: formatDate(period.date_to) })} change={yoy(kpis.closing, kpis.closing_prev, year)} hint={formula('closing')} />
      <Tile icon="diff" label={t('obzor.kpi.diff')} value={kpis.diff} note={t('obzor.kpi.diffNote')} change={yoy(kpis.diff, kpis.diff_prev, year)} hint={formula('diff')} />
    </KpiGrid>
  );
}
