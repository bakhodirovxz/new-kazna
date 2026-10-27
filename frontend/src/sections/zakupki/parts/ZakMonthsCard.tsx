import { useMemo, useRef } from 'react';
import type { ZakMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `zakMonthly`: сумма договоров по дате заключения. */
export function ZakMonthsCard({ months, ctx, className }: { months: ZakMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('zak.months.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const color = COLORS.in();
  const config = useMemo(
    () => barConfig({ labels: months.map((m) => monthShort(m.month_id)), series: [{ label: t('zak.months.value'), data: months.map((m) => m.contracted), color }] }),
    [months, color],
  );
  const table = { headers: [t('zak.months.month'), t('zak.months.value')], rows: months.map((m) => [monthShort(m.month_id), m.contracted]) };
  return (
    <Card className={className} title={title} sub={t('zak.months.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
