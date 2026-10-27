import type { LoanRowOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

function Repaid({ share }: { share: number | null }) {
  return (
    <span className="exec">
      {formatPct(share, 1)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, Math.max(0, (share ?? 0) * 100))}%` }} />
      </i>
    </span>
  );
}

function grace(row: LoanRowOut) {
  if (!row.grace_until) return '—';
  return row.in_grace ? <Badge tone="blue">{t('kredity.registry.graceUntil', { year: row.grace_until.slice(0, 4) })}</Badge> : <Badge>{t('kredity.registry.graceDone')}</Badge>;
}

export interface LoanRegistryProps {
  loans: LoanRowOut[];
  asOf: string;
  ctx: ExportContext;
  filters: FilterState;
  onBranch(br: number | null): void;
  className?: string;
}

/** TZ 5: реестр кредитов с условиями и долей погашения; нажатие на строку выбирает филиал (TZ 6). */
export function LoanRegistry({ loans, asOf, ctx, filters, onBranch, className }: LoanRegistryProps) {
  const title = t('kredity.registry.title');
  const total = loans.reduce((s, r) => s + (r.outstanding ?? 0), 0);
  const columns: Column<LoanRowOut>[] = [
    { key: 'creditor', header: t('kredity.registry.creditor'), cell: (r) => r.creditor, sortValue: (r) => r.creditor, wrap: true },
    {
      key: 'project',
      header: t('kredity.registry.project'),
      cell: (r) => (
        <>
          {r.project}
          <br />
          <span className="note">{r.branch_name}</span>
        </>
      ),
      wrap: true,
    },
    { key: 'currency', header: t('kredity.registry.currency'), cell: (r) => r.currency, sortValue: (r) => r.currency },
    { key: 'rate', header: t('kredity.registry.rate'), cell: (r) => formatPct(r.rate, 1), sortValue: (r) => r.rate, align: 'right' },
    {
      key: 'outstanding',
      header: t('kredity.registry.outstanding'),
      cell: (r) => <b>{r.outstanding === null ? t('kredity.upcoming.noRate') : formatMoney(r.outstanding)}</b>,
      sortValue: (r) => r.outstanding,
      align: 'right',
    },
    { key: 'repaid', header: t('kredity.registry.repaid'), cell: (r) => <Repaid share={r.repaid_share} />, sortValue: (r) => r.repaid_share, align: 'right' },
    { key: 'grace', header: t('kredity.registry.grace'), cell: grace },
    { key: 'maturity', header: t('kredity.registry.maturity'), cell: (r) => r.maturity.slice(0, 4), sortValue: (r) => r.maturity, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('kredity.registry.sub', { date: formatDate(asOf) })}
      exportSlot={
        <CardExport
          title={title}
          ctx={ctx}
          csv={() => ({
            headers: [t('kredity.registry.creditor'), t('kredity.registry.project'), t('kredity.registry.currency'), t('kredity.registry.rate'), t('kredity.registry.outstanding'), t('kredity.registry.repaid'), t('kredity.registry.maturity')],
            rows: loans.map((r) => [r.creditor, r.project, r.currency, Math.round(r.rate * 10000) / 100, r.outstanding, r.repaid_share === null ? null : Math.round(r.repaid_share * 1000) / 10, formatDate(r.maturity)]),
          })}
        />
      }
    >
      <Table
        caption={title}
        columns={columns}
        rows={loans}
        rowKey={(r) => r.loan_id}
        onRowClick={(r) => toggleBranch(filters, r.branch_id, onBranch)}
        free
        footer={
          <tr>
            <td colSpan={4}>{t('kredity.registry.total')}</td>
            <td>
              <b>{formatMoney(total)}</b>
            </td>
            <td colSpan={3} />
          </tr>
        }
      />
    </Card>
  );
}
