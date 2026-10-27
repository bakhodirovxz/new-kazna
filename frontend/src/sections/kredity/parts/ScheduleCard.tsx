import { useMemo, useRef } from 'react';
import type { LoanYearOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

const PRINCIPAL = '#0b4fa8';
const INTEREST = '#5fd0e0';

/** TZ 5: график погашения на 10 лет с разделением основного долга и процентов. */
export function ScheduleCard({ years, ctx, className }: { years: LoanYearOut[]; ctx: ExportContext; className?: string }) {
  const title = t('kredity.schedule.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const config = useMemo(
    () =>
      barConfig({
        labels: years.map((y) => String(y.year)),
        series: [
          { label: t('kredity.schedule.principal'), data: years.map((y) => y.principal), color: PRINCIPAL },
          { label: t('kredity.schedule.interest'), data: years.map((y) => y.interest), color: INTEREST },
        ],
        stacked: true,
      }),
    [years],
  );
  const table = {
    headers: [t('kredity.schedule.year'), t('kredity.schedule.principal'), t('kredity.schedule.interest')],
    rows: years.map((y) => [String(y.year), y.principal, y.interest]),
  };
  return (
    <Card className={className} title={title} sub={t('kredity.schedule.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('debtService')}>
        <span>
          <i style={{ background: PRINCIPAL }} />
          {t('kredity.schedule.principal')}
        </span>
        <span>
          <i style={{ background: INTEREST }} />
          {t('kredity.schedule.interest')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
