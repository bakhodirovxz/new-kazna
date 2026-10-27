import type { StockBranchOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney } from '../../../dash/money';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

/** Prototip `whBrTable` (TZ 5 «склады филиалов»): bosish — filial tanlash (TZ 6). */
export function StockBranchesTable({ rows, ctx, filters, onBranch, className }: { rows: StockBranchOut[]; ctx: ExportContext; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('sklad.branches.title');
  const headers = [t('sklad.col.warehouse'), t('sklad.col.value'), t('sklad.branches.positions'), t('sklad.branches.below'), t('sklad.branches.idle')];
  const columns: Column<StockBranchOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (r) => r.name, sortValue: (r) => r.name, wrap: true },
    { key: 'value', header: headers[1] ?? '', cell: (r) => formatMoney(r.value), sortValue: (r) => r.value, align: 'right' },
    { key: 'positions', header: headers[2] ?? '', cell: (r) => String(r.positions), sortValue: (r) => r.positions, align: 'right' },
    { key: 'below', header: headers[3] ?? '', cell: (r) => <span className={r.below_min > 1 ? 'neg' : undefined}>{r.below_min}</span>, sortValue: (r) => r.below_min, align: 'right' },
    { key: 'idle', header: headers[4] ?? '', cell: (r) => formatMoney(r.idle_value), sortValue: (r) => r.idle_value, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('sklad.branches.sub')}
      exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((r) => [r.name, r.value, r.positions, r.below_min, r.idle_value]) })} />}
    >
      <Table caption={title} columns={columns} rows={rows} rowKey={(r) => r.branch_id} onRowClick={(r) => toggleBranch(filters, r.branch_id, onBranch)} free />
    </Card>
  );
}
