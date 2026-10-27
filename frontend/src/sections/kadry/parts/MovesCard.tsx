import { useMemo, useRef } from 'react';
import type { HrMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { formatPeople } from '../../../dash/people';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `movCard`: приём и увольнение по месяцам. */
export function MovesCard({ months, ctx, className }: { months: HrMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('kad.mov.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const hired = COLORS.in();
  const fired = COLORS.out();
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('kad.mov.hired'), data: months.map((m) => m.hired ?? Number.NaN), color: hired },
          { label: t('kad.mov.fired'), data: months.map((m) => m.fired ?? Number.NaN), color: fired },
        ],
        format: (v) => formatPeople(v),
      }),
    [months, hired, fired],
  );
  const table = { headers: [t('kad.fot.month'), t('kad.mov.hired'), t('kad.mov.fired')], rows: months.map((m) => [monthShort(m.month_id), m.hired, m.fired]) };
  return (
    <Card className={className} title={title} sub={t('kad.mov.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('staffTurnover')}>
        <span>
          <i style={{ background: hired }} />
          {t('kad.mov.hired')}
        </span>
        <span>
          <i style={{ background: fired }} />
          {t('kad.mov.fired')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} format={(v) => formatPeople(v)} />
    </Card>
  );
}
