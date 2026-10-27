import type { ZakBranchOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

function Exec({ value }: { value: number | null }) {
  return (
    <span className="exec">
      {formatPct(value, 0)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, Math.max(0, (value ?? 0) * 100))}%` }} />
      </i>
    </span>
  );
}

/** Prototip «Закупки по филиалам»: годовой план, заключено с начала года, исполнение, экономия. */
export function ZakBranchesTable({ rows, ctx, filters, onBranch, className }: { rows: ZakBranchOut[]; ctx: ExportContext; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('zak.branches.title');
  const headers = [t('zak.col.branch'), t('zak.branches.plan'), t('zak.branches.ytd'), t('zak.branches.exec'), t('zak.branches.savings')];
  const columns: Column<ZakBranchOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (b) => b.name, sortValue: (b) => b.name, wrap: true },
    { key: 'plan', header: headers[1] ?? '', cell: (b) => formatMoney(b.plan), sortValue: (b) => b.plan, align: 'right' },
    { key: 'ytd', header: headers[2] ?? '', cell: (b) => formatMoney(b.ytd), sortValue: (b) => b.ytd, align: 'right' },
    { key: 'exec', header: headers[3] ?? '', cell: (b) => <Exec value={b.execution} />, sortValue: (b) => b.execution, align: 'right' },
    { key: 'savings', header: headers[4] ?? '', cell: (b) => formatMoney(b.savings), sortValue: (b) => b.savings, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('zak.branches.sub')}
      exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((b) => [b.name, b.plan, b.ytd, b.execution === null ? null : Math.round(b.execution * 1000) / 10, b.savings]) })} />}
    >
      <Table caption={title} columns={columns} rows={rows} rowKey={(b) => b.branch_id} onRowClick={(b) => toggleBranch(filters, b.branch_id, onBranch)} free />
    </Card>
  );
}
