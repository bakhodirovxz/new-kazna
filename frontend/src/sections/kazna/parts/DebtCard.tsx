import { useState } from 'react';
import type { ContractRowOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { NoData } from '../../../dash/DataState';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney } from '../../../dash/money';
import { t, type MessageKey } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import { buildHash } from '../../../router/hash';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';

type DebtFilter = 'all' | 'receivable' | 'payable' | 'overdue';
const FILTERS: DebtFilter[] = ['all', 'receivable', 'payable', 'overdue'];

function term(c: ContractRowOut): string {
  if (c.overdue_days > 0) return t('kazna.debt.late', { days: c.overdue_days });
  return c.end_date ? t('kazna.debt.until', { date: formatDate(c.end_date) }) : '—';
}

/** TZ 5: реестр крупнейших договоров с фильтром; просроченные первыми (tartib — serverdan). */
export function DebtCard({ contracts, limit, hasData, ctx, className }: { contracts: ContractRowOut[]; limit?: number; hasData: boolean; ctx: ExportContext; className?: string }) {
  const [filter, setFilter] = useState<DebtFilter>('all');
  const title = t('kazna.debt.title');
  const rows = contracts
    .filter((c) => filter === 'all' || (filter === 'overdue' ? c.overdue_days > 0 : c.kind === filter))
    .slice(0, limit ?? contracts.length);
  const columns: Column<ContractRowOut>[] = [
    { key: 'cp', header: t('kazna.debt.cp'), cell: (c) => c.cp_name, wrap: true },
    { key: 'number', header: t('kazna.debt.contract'), cell: (c) => c.number },
    { key: 'branch', header: t('dash.branch'), cell: (c) => c.branch_name, wrap: true },
    { key: 'kind', header: t('kazna.debt.kind'), cell: (c) => t(`kazna.debt.${c.kind}` as MessageKey) },
    { key: 'amount', header: t('dash.amount'), cell: (c) => <b>{formatMoney(c.amount)}</b>, align: 'right' },
    { key: 'term', header: t('kazna.debt.term'), cell: (c) => <Badge tone={c.overdue_days > 0 ? 'neg' : 'neutral'}>{term(c)}</Badge> },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={limit ? t('kazna.debt.subTop') : t('kazna.debt.sub')}
      actions={
        <div className="seg" role="group" aria-label={t('kazna.debt.filter')}>
          {FILTERS.map((f) => (
            <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {t(`kazna.debt.${f}` as MessageKey)}
            </button>
          ))}
        </div>
      }
      exportSlot={
        hasData ? (
          <CardExport
            title={title}
            ctx={ctx}
            csv={() => ({
              headers: [t('kazna.debt.cp'), t('kazna.debt.contract'), t('dash.branch'), t('kazna.debt.kind'), t('dash.amount'), t('kazna.debt.term')],
              rows: rows.map((c) => [c.cp_name, c.number, c.branch_name, t(`kazna.debt.${c.kind}` as MessageKey), c.amount, term(c)]),
            })}
          />
        ) : undefined
      }
    >
      {hasData ? (
        <Table caption={title} columns={columns} rows={rows} rowKey={(c) => c.contract_id} free empty={<p className="note">{t('kazna.debt.none')}</p>} />
      ) : (
        <NoData kind="source" source={t('dash.source.debt')} />
      )}
      {limit ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'kazna', page: 'dogovory', br: ctx.br, per: ctx.per })}>
          {t('kazna.debt.allContracts')}
        </a>
      ) : null}
    </Card>
  );
}
