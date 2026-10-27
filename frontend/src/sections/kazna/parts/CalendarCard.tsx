import { useMemo, useRef } from 'react';
import type { CalendarOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, type ChartHandle } from '../../../dash/chart';
import { NoData } from '../../../dash/DataState';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import { t, type MessageKey } from '../../../i18n';
import { formatDate, formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

const KINDS = ['taxes', 'salary', 'loans', 'contracts'] as const;
const COLORS = ['#0b4fa8', '#2f8ef5', '#5fd0e0', '#9dc0e8'];
const WEEKDAYS = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

function dayLabel(iso: string): string[] {
  const d = new Date(`${iso}T00:00:00Z`);
  return [`${iso.slice(8, 10)}.${iso.slice(5, 7)}`, WEEKDAYS[d.getUTCDay()] ?? ''];
}

/** TZ 5: 14 дней вперёд по видам платежей, сумма к оплате, остаток и во сколько раз он покрывает платежи. */
export function CalendarCard({ calendar, ctx, className }: { calendar: CalendarOut; ctx: ExportContext; className?: string }) {
  const title = t('kazna.calendar.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const config = useMemo(
    () =>
      barConfig({
        labels: calendar.days.map((d) => dayLabel(d.date)),
        series: KINDS.map((k, i) => ({ label: t(`kazna.calendar.${k}` as MessageKey), data: calendar.days.map((d) => d[k]), color: COLORS[i] ?? '#999999' })),
        stacked: true,
      }),
    [calendar],
  );
  const table = {
    headers: [t('kazna.calendar.day'), ...KINDS.map((k) => t(`kazna.calendar.${k}` as MessageKey))],
    rows: calendar.days.map((d) => [formatDate(d.date), ...KINDS.map((k) => d[k])]),
  };
  const empty = calendar.as_of === null || calendar.total === 0;
  const cover = calendar.coverage;
  return (
    <Card
      className={className}
      title={title}
      sub={calendar.start ? t('kazna.calendar.sub', { date: formatDate(calendar.start) }) : undefined}
      exportSlot={empty ? undefined : <CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}
    >
      {empty ? (
        <NoData kind="source" source={t('dash.source.calendar')} />
      ) : (
        <>
          <div className="cover" title={formula('coverage')}>
            <div>
              <span>{t('kazna.calendar.toPay')}</span>
              <b>{formatMoney(calendar.total)}</b>
            </div>
            <div>
              <span>{t('kazna.calendar.balance')}</span>
              <b>{formatMoney(calendar.balance)}</b>
            </div>
            <div>
              <span>{t('kazna.calendar.coverage')}</span>
              <b className={cover !== null && cover < 1 ? 'neg' : undefined}>
                {cover === null ? '—' : cover >= 1 ? t('kazna.calendar.times', { value: formatNumber(cover, 1) }) : t('kazna.calendar.part', { value: formatPct(cover, 0) })}
              </b>
            </div>
          </div>
          <div className="legend">
            {KINDS.map((k, i) => (
              <span key={k}>
                <i style={{ background: COLORS[i] }} />
                {t(`kazna.calendar.${k}` as MessageKey)}
              </span>
            ))}
          </div>
          <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
        </>
      )}
    </Card>
  );
}
