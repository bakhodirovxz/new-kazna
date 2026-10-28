import { useMemo, useRef } from 'react';
import type { FinYearOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, cssColor, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

interface ChartProps {
  years: FinYearOut[];
  ctx: ExportContext;
  className?: string;
}

const labels = (years: FinYearOut[]) => years.map((y) => String(y.year));

function Legend({ items }: { items: Array<{ label: string; color: string; line?: boolean }> }) {
  return (
    <div className="legend">
      {items.map((x) => (
        <span key={x.label}>
          <i className={x.line ? 'is-line' : undefined} style={{ background: x.color }} />
          {x.label}
        </span>
      ))}
    </div>
  );
}

/** Выручка и EBITDA — ustunlar, рентабельность — chiziq o'ng o'qda. */
export function RevenueCard({ years, ctx, className }: ChartProps) {
  const title = t('fm.rev.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const rev = COLORS.in();
  const ebitda = COLORS.v2();
  const margin = COLORS.bal();
  const config = useMemo(
    () =>
      barConfig({
        labels: labels(years),
        series: [
          { label: t('fm.rev.revenue'), data: years.map((y) => y.revenue), color: rev },
          { label: t('fm.rev.ebitda'), data: years.map((y) => y.ebitda), color: ebitda },
          { label: t('fm.rev.margin'), data: years.map((y) => (y.margin === null ? Number.NaN : y.margin * 100)), color: margin, type: 'line', axis: 'right' },
        ],
        rightFormat: (v, d) => `${formatNumber(v, d)}%`,
      }),
    [years, rev, ebitda, margin],
  );
  const table = { headers: [t('fm.col.year'), t('fm.rev.revenue'), t('fm.rev.ebitda'), t('fm.rev.margin')], rows: years.map((y) => [y.year, y.revenue, y.ebitda, y.margin === null ? null : Math.round(y.margin * 1000) / 10]) };
  return (
    <Card className={className} title={title} sub={t('fm.rev.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div title={formula('finMargin')}>
        <Legend items={[{ label: t('fm.rev.revenue'), color: rev }, { label: t('fm.rev.ebitda'), color: ebitda }, { label: t('fm.rev.margin'), color: margin, line: true }]} />
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}

/** EBITDA (+), инвестиции и обслуживание долга (−) — stacked; остаток — chiziq. */
export function CashFlowCard({ years, ctx, className }: ChartProps) {
  const title = t('fm.cash.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const ebitda = COLORS.in();
  const capex = COLORS.prev();
  const debt = COLORS.v2();
  const balance = COLORS.bal();
  const config = useMemo(
    () =>
      barConfig({
        labels: labels(years),
        stacked: true,
        series: [
          { label: t('fm.rev.ebitda'), data: years.map((y) => y.ebitda), color: ebitda },
          { label: t('fm.cash.capex'), data: years.map((y) => -y.capex), color: capex },
          { label: t('fm.cash.debt'), data: years.map((y) => -y.debt_service), color: debt },
          { label: t('fm.cash.balance'), data: years.map((y) => y.balance), color: balance, type: 'line' },
        ],
      }),
    [years, ebitda, capex, debt, balance],
  );
  const table = { headers: [t('fm.col.year'), t('fm.rev.ebitda'), t('fm.cash.capex'), t('fm.cash.debt'), t('fm.col.net'), t('fm.cash.balance')], rows: years.map((y) => [y.year, y.ebitda, y.capex, y.debt_service, y.net_flow, y.balance]) };
  return (
    <Card className={className} title={title} sub={t('fm.cash.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div title={formula('finNetFlow')}>
        <Legend items={[{ label: t('fm.rev.ebitda'), color: ebitda }, { label: t('fm.cash.capex'), color: capex }, { label: t('fm.cash.debt'), color: debt }, { label: t('fm.cash.balance'), color: balance, line: true }]} />
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}

/** Операционные расходы, налоги и EBITDA в составе выручки (stacked). */
export function StructureCard({ years, ctx, className }: ChartProps) {
  const title = t('fm.struct.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const opex = COLORS.v2();
  const tax = COLORS.prev();
  const ebitda = COLORS.in();
  const config = useMemo(
    () =>
      barConfig({
        labels: labels(years),
        stacked: true,
        series: [
          { label: t('fm.struct.opex'), data: years.map((y) => y.opex), color: opex },
          { label: t('fm.struct.tax'), data: years.map((y) => y.tax), color: tax },
          { label: t('fm.rev.ebitda'), data: years.map((y) => y.ebitda), color: ebitda },
        ],
      }),
    [years, opex, tax, ebitda],
  );
  const table = { headers: [t('fm.col.year'), t('fm.struct.opex'), t('fm.struct.tax'), t('fm.rev.ebitda'), t('fm.rev.revenue')], rows: years.map((y) => [y.year, y.opex, y.tax, y.ebitda, y.revenue]) };
  return (
    <Card className={className} title={title} sub={t('fm.struct.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <Legend items={[{ label: t('fm.struct.opex'), color: opex }, { label: t('fm.struct.tax'), color: tax }, { label: t('fm.rev.ebitda'), color: ebitda }]} />
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}

/** DSCR chizig'i va ковенант chegarasi (uzuk-uzuk, qizil). */
export function DscrChartCard({ years, covenant, ctx, className }: ChartProps & { covenant: number }) {
  const title = t('fm.dscr.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const line = COLORS.in();
  const neg = cssColor('--neg', '#c9362c');
  const threshold = t('fm.dscr.threshold', { covenant: formatNumber(covenant, 2) });
  const config = useMemo(
    () =>
      barConfig({
        labels: labels(years),
        format: (v, d) => formatNumber(v, Math.max(d, 1)),
        series: [
          { label: t('fm.col.dscr'), data: years.map((y) => y.dscr ?? Number.NaN), color: line, type: 'line' },
          { label: threshold, data: years.map(() => covenant), color: neg, type: 'line', dashed: true },
        ],
      }),
    [years, covenant, line, neg, threshold],
  );
  const table = { headers: [t('fm.col.year'), t('fm.col.dscr')], rows: years.map((y) => [y.year, y.dscr]) };
  return (
    <Card className={className} title={title} sub={t('fm.dscr.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div title={formula('dscr')}>
        <Legend items={[{ label: t('fm.col.dscr'), color: line, line: true }, { label: threshold, color: neg, line: true }]} />
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
