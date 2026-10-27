import type { ZakKpisOut, ZakLotOut, ZakMethodOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import { formatDays } from '../../../dash/people';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';

/** Prototip `ecoTable`: экономия по способам закупки. */
export function EconomyTable({ methods, ctx, className }: { methods: ZakMethodOut[]; ctx: ExportContext; className?: string }) {
  const title = t('zak.eco.title');
  const headers = [t('zak.col.method'), t('zak.eco.lots'), t('zak.col.start'), t('zak.eco.contracts'), t('zak.kpi.savings'), t('zak.eco.share')];
  const columns: Column<ZakMethodOut>[] = [
    { key: 'title', header: headers[0] ?? '', cell: (m) => m.title, sortValue: (m) => m.title },
    { key: 'lots', header: headers[1] ?? '', cell: (m) => formatNumber(m.lots), sortValue: (m) => m.lots, align: 'right' },
    { key: 'start', header: headers[2] ?? '', cell: (m) => formatMoney(m.start), sortValue: (m) => m.start, align: 'right' },
    { key: 'contracted', header: headers[3] ?? '', cell: (m) => formatMoney(m.contracted), sortValue: (m) => m.contracted, align: 'right' },
    { key: 'savings', header: headers[4] ?? '', cell: (m) => <b>{formatMoney(m.savings)}</b>, sortValue: (m) => m.savings, align: 'right' },
    { key: 'share', header: headers[5] ?? '', cell: (m) => formatPct(m.savings_share, 1), sortValue: (m) => m.savings_share, align: 'right' },
  ];
  return (
    <Card className={className} title={title} sub={t('zak.eco.sub')} exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: methods.map((m) => [m.title, m.lots, m.start, m.contracted, m.savings, m.savings_share]) })} />}>
      <div title={formula('savings')}>
        <Table caption={title} columns={columns} rows={methods} rowKey={(m) => m.method} free />
      </div>
    </Card>
  );
}

/** Prototip «Отменённые лоты». */
export function CancelledCard({ lots, className }: { lots: ZakLotOut[]; className?: string }) {
  const title = t('zak.cancelled.title');
  const columns: Column<ZakLotOut>[] = [
    { key: 'lot', header: t('zak.col.lot'), cell: (l) => l.lot_no },
    { key: 'subject', header: t('zak.col.subject'), cell: (l) => l.subject, wrap: true },
    { key: 'branch', header: t('zak.col.branch'), cell: (l) => l.branch_name, wrap: true },
    { key: 'start', header: t('zak.col.start'), cell: (l) => formatMoney(l.start_price), align: 'right' },
  ];
  return (
    <Card className={className} title={title} sub={t('zak.cancelled.sub')}>
      {lots.length ? <Table caption={title} columns={columns} rows={lots} rowKey={(l) => `${l.branch_id}:${l.lot_no}`} free /> : <p className="note">{t('zak.cancelled.none')}</p>}
    </Card>
  );
}

/** Prototip «Средний срок закупки»: среднее по договорам и по способам (норматив — в подписи). */
export function AvgDaysCard({ kpis, methods, className }: { kpis: ZakKpisOut; methods: ZakMethodOut[]; className?: string }) {
  const title = t('zak.days.title');
  const avg = kpis.avg_days;
  return (
    <Card className={className} title={title} sub={t('zak.days.sub')}>
      <div className="bigline" title={formula('avgProcDays')}>
        <b>{avg === null ? t('dash.noValue') : `${formatNumber(avg, 1)} ${t('unit.dayShort')}`}</b>
        <span>{t('zak.days.avg')}</span>
      </div>
      <Rank
        label={title}
        items={methods.filter((m) => m.avg_days !== null).map((m) => ({ id: m.method, name: m.title, value: m.avg_days ?? 0, ...(m.norm_days === null ? {} : { note: t('zak.days.norm', { norm: m.norm_days }) }) }))}
        format={(v) => formatDays(v)}
      />
    </Card>
  );
}
