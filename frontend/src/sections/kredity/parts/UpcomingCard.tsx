import type { LoanPaymentOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import { buildHash } from '../../../router/hash';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';

function amount(value: number | null): string {
  return value === null ? t('kredity.upcoming.noRate') : formatMoney(value);
}

export interface UpcomingCardProps {
  payments: LoanPaymentOut[];
  title: string;
  sub: string;
  ctx: ExportContext;
  className?: string;
  more?: boolean;
}

/** Prototip `upcomingList`: ближайшие платежи по графику (дата, кредитор, основной долг, проценты). */
export function UpcomingCard({ payments, title, sub, ctx, className, more = false }: UpcomingCardProps) {
  const headers = [t('kredity.upcoming.date'), t('kredity.upcoming.creditor'), t('kredity.schedule.principal'), t('kredity.schedule.interest'), t('kredity.upcoming.total')];
  const columns: Column<LoanPaymentOut>[] = [
    { key: 'day', header: headers[0] ?? '', cell: (p) => formatDate(p.day), sortValue: (p) => p.day },
    {
      key: 'creditor',
      header: headers[1] ?? '',
      cell: (p) => (
        <>
          {p.creditor}
          <br />
          <span className="note">{p.project}</span>
        </>
      ),
      sortValue: (p) => p.creditor,
      wrap: true,
    },
    { key: 'principal', header: headers[2] ?? '', cell: (p) => amount(p.principal), sortValue: (p) => p.principal, align: 'right' },
    { key: 'interest', header: headers[3] ?? '', cell: (p) => amount(p.interest), sortValue: (p) => p.interest, align: 'right' },
    { key: 'total', header: headers[4] ?? '', cell: (p) => <b>{amount(p.total)}</b>, sortValue: (p) => p.total, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={sub}
      exportSlot={
        payments.length ? (
          <CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: payments.map((p) => [formatDate(p.day), p.creditor, p.principal, p.interest, p.total]) })} />
        ) : undefined
      }
    >
      <Table caption={title} columns={columns} rows={payments} rowKey={(p) => `${p.day}-${p.loan_id}`} free empty={<p className="note">{t('kredity.upcoming.none')}</p>} />
      {more ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'kredity', page: 'grafik', br: ctx.br, per: ctx.per })}>
          {t('kredity.upcoming.all')}
        </a>
      ) : null}
    </Card>
  );
}
