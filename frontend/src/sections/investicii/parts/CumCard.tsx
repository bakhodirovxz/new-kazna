import { useMemo, useRef } from 'react';
import type { InvCumOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import '../../../dash/s4.css';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `invCum`: план (uzuk-uzuk) va факт нарастающим итогом; fakt — joriy oygacha. */
export function CumCard({ points, ctx, className }: { points: InvCumOut[]; ctx: ExportContext; className?: string }) {
  const title = t('inv.cum.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const plan = COLORS.bal();
  const fact = COLORS.in();
  const config = useMemo(
    () =>
      barConfig({
        labels: points.map((p) => monthShort(p.month_id)),
        series: [
          { label: t('inv.cum.plan'), data: points.map((p) => p.plan), color: plan, type: 'line', dashed: true },
          { label: t('inv.cum.fact'), data: points.map((p) => p.fact ?? Number.NaN), color: fact, type: 'line' },
        ],
      }),
    [points, plan, fact],
  );
  const table = { headers: [t('inv.cum.month'), t('inv.cum.plan'), t('inv.cum.fact')], rows: points.map((p) => [monthShort(p.month_id), p.plan, p.fact]) };
  return (
    <Card className={className} title={title} sub={t('inv.cum.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('schedule')}>
        <span>
          <i className="dash" style={{ background: plan }} />
          {t('inv.cum.plan')}
        </span>
        <span>
          <i style={{ background: fact }} />
          {t('inv.cum.fact')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
