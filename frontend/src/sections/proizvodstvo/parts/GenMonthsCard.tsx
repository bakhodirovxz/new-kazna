import { useMemo, useRef } from 'react';
import type { GenMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import { formatKwh } from '../../../dash/energy';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `genCard`: факт — ustun, план — uzuk-uzuk chiziq; CSV'da o'tgan yil ham. */
export function GenMonthsCard({ months, ctx, className }: { months: GenMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('proizv.months.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const fact = COLORS.in();
  const plan = COLORS.bal();
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('proizv.months.fact'), data: months.map((m) => m.generation), color: fact },
          { label: t('proizv.months.plan'), data: months.map((m) => m.plan), color: plan, type: 'line', dashed: true },
        ],
        format: formatKwh,
      }),
    [months, fact, plan],
  );
  const table = {
    headers: [t('proizv.months.month'), t('proizv.months.fact'), t('proizv.months.plan'), t('proizv.months.prev')],
    rows: months.map((m) => [monthShort(m.month_id), m.generation, m.plan, m.generation_prev]),
  };
  return (
    <Card className={className} title={title} sub={t('proizv.months.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('genPlan')}>
        <span>
          <i style={{ background: fact }} />
          {t('proizv.months.fact')}
        </span>
        <span>
          <i className="dash" style={{ background: plan }} />
          {t('proizv.months.plan')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} format={formatKwh} />
    </Card>
  );
}
