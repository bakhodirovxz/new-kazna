import { useMemo, useRef } from 'react';
import type { SalesMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `salesCard`: начислено за отпущенную энергию и оплачено покупателем по месяцам. */
export function SalesMonthsCard({ months, ctx, className }: { months: SalesMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('proizv.sales.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const accrued = COLORS.out();
  const paid = COLORS.in();
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('proizv.sales.accrued'), data: months.map((m) => m.accrued), color: accrued },
          { label: t('proizv.sales.paid'), data: months.map((m) => m.paid), color: paid },
        ],
      }),
    [months, accrued, paid],
  );
  const table = {
    headers: [t('proizv.months.month'), t('proizv.sales.accrued'), t('proizv.sales.paid')],
    rows: months.map((m) => [monthShort(m.month_id), m.accrued, m.paid]),
  };
  return (
    <Card className={className} title={title} sub={t('proizv.sales.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('paymentLevel')}>
        <span>
          <i style={{ background: accrued }} />
          {t('proizv.sales.accrued')}
        </span>
        <span>
          <i style={{ background: paid }} />
          {t('proizv.sales.paid')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
