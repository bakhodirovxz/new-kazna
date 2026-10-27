import { useMemo, useRef } from 'react';
import type { StockMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `whFlowCard`: поступление и списание запасов по месяцам. */
export function StockFlowCard({ months, ctx, className }: { months: StockMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('sklad.flow.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const inColor = COLORS.in();
  const outColor = COLORS.out();
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('sklad.flow.in'), data: months.map((m) => m.inflow), color: inColor },
          { label: t('sklad.flow.out'), data: months.map((m) => m.outflow), color: outColor },
        ],
      }),
    [months, inColor, outColor],
  );
  const table = {
    headers: [t('sklad.flow.month'), t('sklad.flow.in'), t('sklad.flow.out')],
    rows: months.map((m) => [monthShort(m.month_id), m.inflow, m.outflow]),
  };
  return (
    <Card className={className} title={title} sub={t('sklad.flow.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('stockFlow')}>
        <span>
          <i style={{ background: inColor }} />
          {t('sklad.flow.in')}
        </span>
        <span>
          <i style={{ background: outColor }} />
          {t('sklad.flow.out')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
