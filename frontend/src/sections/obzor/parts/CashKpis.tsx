import type { CashKpisOut, ReportPeriodOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { formula } from '../../../dash/formulas';
import { formatDelta, moneyParts, yoyRatio } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import { Card } from '../../../ui/Card';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';
import type { IconName } from '../../../ui/icons';

interface Yoy {
  text: string;
  good: boolean;
}

/** `inverse` — расходование: меньше трат, чем год назад, это хорошо (ruling A-S1.R2). */
function yoy(cur: number | null, prev: number | null, year: number, inverse = false): Yoy | null {
  if (cur === null) return null;
  const ratio = yoyRatio(cur, prev);
  if (ratio === null) return null;
  return { text: t('dash.yoy', { year, delta: formatDelta(ratio) }), good: inverse ? ratio <= 0 : ratio >= 0 };
}

function Tile({ icon, label, value, note, reason, change, hint, signed }: { icon: IconName; label: string; value: number | null; note: string; reason: string; change: Yoy | null; hint: string; signed?: boolean }) {
  const parts = value === null ? null : moneyParts(value);
  // Пустое значение: «нет данных» + причина (правило пустых состояний).
  const delta = value === null ? reason : change ? <>{note} · <span className={change.good ? 'yoy yoy--good' : 'yoy yoy--bad'}>{change.text}</span></> : note;
  return (
    <KpiTile
      icon={icon}
      label={label}
      value={parts ? `${signed && value !== null && value > 0 ? '+' : ''}${parts.value}` : t('dash.noValue')}
      unit={parts?.unit}
      negative={value !== null && value < 0}
      delta={delta}
      hint={`${hint}. ${formula('yoy')}`}
    />
  );
}

/** TZ 5 «Сводка»: шесть показателей движения денежных средств с изменением к прошлому году. */
export function CashKpis({ kpis, period }: { kpis: CashKpisOut; period: ReportPeriodOut }) {
  const year = Number(period.date_from.slice(0, 4)) - 1;
  // Движение за период отсутствует — не показываем нули и «−100% к прошлому году».
  const flow = (v: number | null) => (kpis.has_data ? v : null);
  const noPeriod = t('obzor.kpi.noPeriod');
  const noBalances = t('obzor.kpi.noBalances');
  return (
    <>
      <KpiGrid>
        <Tile icon="cal" label={t('obzor.kpi.opening')} value={kpis.opening} note={t('obzor.kpi.at', { date: formatDate(period.date_from) })} reason={noBalances} change={yoy(kpis.opening, kpis.opening_prev, year)} hint={formula('opening')} />
        <Tile icon="in" label={t('obzor.kpi.inflow')} value={flow(kpis.inflow)} note={t('obzor.kpi.period')} reason={noPeriod} change={yoy(flow(kpis.inflow), kpis.inflow_prev, year)} hint={formula('inflow')} />
        <Tile icon="out" label={t('obzor.kpi.outflow')} value={flow(kpis.outflow)} note={t('obzor.kpi.period')} reason={noPeriod} change={yoy(flow(kpis.outflow), kpis.outflow_prev, year, true)} hint={formula('outflow')} />
        <Tile icon="net" label={t('obzor.kpi.net')} value={flow(kpis.net)} note={t('obzor.kpi.netNote')} reason={noPeriod} change={yoy(flow(kpis.net), kpis.net_prev, year)} hint={formula('net')} signed />
        <Tile icon="check" label={t('obzor.kpi.closing')} value={kpis.closing} note={t('obzor.kpi.closingAt', { date: formatDate(period.date_to) })} reason={noBalances} change={yoy(kpis.closing, kpis.closing_prev, year)} hint={formula('closing')} />
        <Tile icon="diff" label={t('obzor.kpi.diff')} value={kpis.diff} note={t('obzor.kpi.diffNote')} reason={noBalances} change={null} hint={formula('diff')} signed />
      </KpiGrid>
      {kpis.has_data ? null : (
        <Card>
          <NoData kind="period" headingLevel={2} />
        </Card>
      )}
    </>
  );
}
