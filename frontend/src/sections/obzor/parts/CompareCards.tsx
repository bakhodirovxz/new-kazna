import { useMemo, useRef } from 'react';
import type { CashKpisOut, MonthPointOut, ReportPeriodOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formatDelta, formatMoney, yoyRatio } from '../../../dash/money';
import { NoData } from '../../../dash/DataState';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

export function CompareCards({ kpis, months, period, ctx }: { kpis: CashKpisOut; months: MonthPointOut[]; period: ReportPeriodOut; ctx: ExportContext }) {
  const year = Number(period.date_from.slice(0, 4));
  const rows: Array<[string, number, number]> = [
    [t('obzor.kpi.inflow'), kpis.inflow_prev, kpis.inflow],
    [t('obzor.kpi.outflow'), kpis.outflow_prev, kpis.outflow],
    [t('obzor.kpi.net'), kpis.net_prev, kpis.net],
  ];
  const title = t('obzor.compare.title', { year: year - 1 });
  const chartTitle = t('obzor.compare.chartTitle', { year, prev: year - 1 });
  const chartRef = useRef<ChartHandle | null>(null);
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: String(year), data: months.map((m) => m.inflow), color: COLORS.in() },
          { label: String(year - 1), data: months.map((m) => m.inflow_prev), color: COLORS.prev() },
        ],
      }),
    [months, year],
  );
  const table = {
    headers: [t('dash.month'), String(year), String(year - 1)],
    rows: months.map((m) => [monthShort(m.month_id), m.inflow, m.inflow_prev]),
  };
  const noPrev = months.every((m) => !m.inflow_prev && !m.outflow_prev) && rows.every(([, prev]) => !prev);
  return (
    <>
      <Card
        className="c6"
        title={title}
        sub={period.open_last ? t('obzor.compare.subOpen') : t('obzor.compare.sub')}
        exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers: [t('obzor.compare.indicator'), String(year - 1), String(year)], rows: rows.map(([n, a, b]) => [n, a, b]) })} />}
      >
        {noPrev ? <NoData kind="period" headingLevel={3} /> : null}
        <table className="cmp" hidden={noPrev}>
          <caption className="visually-hidden">{title}</caption>
          <thead>
            <tr>
              <th scope="col">{t('obzor.compare.indicator')}</th>
              <th scope="col">{year - 1}</th>
              <th scope="col">{year}</th>
              <th scope="col">{t('obzor.compare.change')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, prev, cur]) => {
              const ratio = yoyRatio(cur, prev);
              return (
                <tr key={name}>
                  <th scope="row">{name}</th>
                  <td>{formatMoney(prev)}</td>
                  <td>
                    <b>{formatMoney(cur)}</b>
                  </td>
                  <td className={ratio !== null && ratio < 0 ? 'neg' : undefined}>{ratio === null ? '—' : formatDelta(ratio)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
      <Card className="c6" title={chartTitle} sub={t('obzor.compare.chartSub')} exportSlot={<CardExport title={chartTitle} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
        {noPrev ? <p className="note">{t('obzor.compare.noPrev', { year: year - 1 })}</p> : <ChartCanvas config={config} label={chartTitle} table={table} size="sm" chartRef={chartRef} />}
      </Card>
    </>
  );
}
