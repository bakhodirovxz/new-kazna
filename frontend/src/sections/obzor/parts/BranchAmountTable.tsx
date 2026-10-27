import type { BranchAmountOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

export interface BranchAmountTableProps {
  title: string;
  label: string;
  rows: BranchAmountOut[];
  filters: FilterState;
  onBranch(br: number | null): void;
  ctx: ExportContext;
  className?: string;
}

/** TZ 6: filial qatorini bosish filtrni tanlaydi, qayta bosish — olib tashlaydi. */
export function BranchAmountTable({ title, label, rows, filters, onBranch, ctx, className }: BranchAmountTableProps) {
  const total = rows.reduce((s, r) => s + r.amount, 0);
  const max = Math.max(1e-9, ...rows.map((r) => r.amount));
  const columns: Column<BranchAmountOut>[] = [
    { key: 'name', header: t('dash.branch'), cell: (r) => r.name, sortValue: (r) => r.name, wrap: true, align: 'left' },
    { key: 'amount', header: label, cell: (r) => formatMoney(r.amount), sortValue: (r) => r.amount, align: 'right' },
    {
      key: 'share',
      header: t('dash.share'),
      align: 'right',
      cell: (r) => (
        <>
          {formatPct(total ? r.amount / total : null)}
          <span className="mini" aria-hidden="true">
            <i style={{ width: `${(r.amount / max) * 100}%` }} />
          </span>
        </>
      ),
    },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('obzor.branches.sub')}
      exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers: [t('dash.branch'), label], rows: rows.map((r) => [r.name, r.amount]) })} />}
    >
      <Table caption={title} columns={columns} rows={rows} rowKey={(r) => r.branch_id} onRowClick={(r) => toggleBranch(filters, r.branch_id, onBranch)} activeKey={filters.br} free bare />
    </Card>
  );
}
