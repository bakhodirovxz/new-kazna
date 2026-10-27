import type { DebtBranchRowOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

export function DebtBranchCard({ rows, date, filters, onBranch, ctx, className }: { rows: DebtBranchRowOut[]; date: string; filters: FilterState; onBranch(br: number | null): void; ctx: ExportContext; className?: string }) {
  const title = t('kazna.debtBranch.title');
  const columns: Column<DebtBranchRowOut>[] = [
    { key: 'name', header: t('dash.branch'), cell: (r) => r.name, sortValue: (r) => r.name, wrap: true, align: 'left' },
    { key: 'rec', header: t('kazna.debt.receivable'), cell: (r) => formatMoney(r.receivable), sortValue: (r) => r.receivable, align: 'right' },
    { key: 'pay', header: t('kazna.debt.payable'), cell: (r) => formatMoney(r.payable), sortValue: (r) => r.payable, align: 'right' },
    {
      key: 'over',
      header: t('kazna.debtBranch.overdue'),
      align: 'right',
      sortValue: (r) => r.overdue_payable,
      cell: (r) => <span className={r.payable > 0 && r.overdue_payable / r.payable > 0.2 ? 'neg' : undefined}>{formatMoney(r.overdue_payable)}</span>,
    },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('kazna.debtBranch.sub', { date: formatDate(date) })}
      exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers: columns.map((c) => c.header), rows: rows.map((r) => [r.name, r.receivable, r.payable, r.overdue_payable]) })} />}
    >
      <Table caption={title} columns={columns} rows={rows} rowKey={(r) => r.branch_id} onRowClick={(r) => toggleBranch(filters, r.branch_id, onBranch)} activeKey={filters.br} free bare />
    </Card>
  );
}
