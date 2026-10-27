import { useMemo, useRef } from 'react';
import type { MonthPointOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

export function FlowCard({ months, ctx, className }: { months: MonthPointOut[]; ctx: ExportContext; className?: string }) {
  const title = t('obzor.flow.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('obzor.kpi.inflow'), data: months.map((m) => m.inflow), color: COLORS.in() },
          { label: t('obzor.kpi.outflow'), data: months.map((m) => m.outflow), color: COLORS.out() },
          { label: t('obzor.flow.balance'), data: months.map((m) => m.closing ?? Number.NaN), color: COLORS.bal(), type: 'line' },
        ],
      }),
    [months],
  );
  const table = {
    headers: [t('dash.month'), t('obzor.kpi.inflow'), t('obzor.kpi.outflow'), t('obzor.flow.balance')],
    rows: months.map((m) => [monthShort(m.month_id), m.inflow, m.outflow, m.closing]),
  };
  return (
    <Card className={className} title={title} sub={t('obzor.flow.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend">
        <span><i style={{ background: COLORS.in() }} />{t('obzor.kpi.inflow')}</span>
        <span><i style={{ background: COLORS.out() }} />{t('obzor.kpi.outflow')}</span>
        <span><i className="is-line" style={{ background: COLORS.bal() }} />{t('obzor.flow.balance')}</span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
