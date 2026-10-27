import { useMemo, useRef } from 'react';
import type { HrMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

/** Prototip `fotCard`: ФОТ — ustunlar, o'rtacha ish haqi — chiziq o'ng o'qda. */
export function FotCard({ months, ctx, className }: { months: HrMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('kad.fot.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const bar = COLORS.in();
  const line = COLORS.bal();
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('kad.fot.payroll'), data: months.map((m) => m.payroll), color: bar },
          { label: t('kad.fot.avg'), data: months.map((m) => m.avg_salary ?? Number.NaN), color: line, type: 'line', axis: 'right' },
        ],
        rightFormat: (v, d) => formatNumber(v, d),
      }),
    [months, bar, line],
  );
  const table = { headers: [t('kad.fot.month'), t('kad.fot.payroll'), t('kad.fot.avg')], rows: months.map((m) => [monthShort(m.month_id), m.payroll, m.avg_salary]) };
  return (
    <Card className={className} title={title} sub={t('kad.fot.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={`${formula('payroll')}. ${formula('avgSalary')}`}>
        <span>
          <i style={{ background: bar }} />
          {t('kad.fot.payroll')}
        </span>
        <span>
          <i className="is-line" style={{ background: line }} />
          {t('kad.fot.avgRight')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
