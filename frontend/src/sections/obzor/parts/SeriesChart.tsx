import { useMemo, useRef } from 'react';
import type { ObzorFlowOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

const IN_SHADES = [COLORS.bal, COLORS.v1, COLORS.v2, COLORS.prev];
const OUT_SHADES = [COLORS.v0, COLORS.v1, COLORS.v2];

/** Oylik stacked grafik: Поступления — 3 statya + qolganlari, Расходование — faoliyat turlari. */
export function SeriesChart({ data, title, sub, ctx, className }: { data: ObzorFlowOut; title: string; sub: string; ctx: ExportContext; className: string }) {
  const chartRef = useRef<ChartHandle | null>(null);
  const colors = useMemo(() => {
    const shades = data.direction === 'out' ? OUT_SHADES : IN_SHADES;
    return data.series.map((_, i) => (shades[i] ?? COLORS.prev)());
  }, [data]);
  const config = useMemo(
    () => barConfig({ labels: data.months.map(monthShort), series: data.series.map((s, i) => ({ label: s.name, data: s.values, color: colors[i] ?? '#999999' })), stacked: true }),
    [data, colors],
  );
  const table = { headers: [t('dash.month'), ...data.series.map((s) => s.name)], rows: data.months.map((m, i) => [monthShort(m), ...data.series.map((s) => s.values[i] ?? 0)]) };
  return (
    <Card className={className} title={title} sub={sub} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend">
        {data.series.map((s, i) => (
          <span key={s.key}>
            <i style={{ background: colors[i] }} />
            {s.name}
          </span>
        ))}
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
