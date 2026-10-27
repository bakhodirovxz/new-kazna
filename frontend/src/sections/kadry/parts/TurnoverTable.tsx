import type { HrBranchOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { cx } from '../../../ui/cx';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

const TURN_HIGH = 0.08; // TZ 4 qoidasi «Текучесть > 8%»

/** Prototip «Текучесть по филиалам»: принято, уволено, текучесть (без пересчёта на год — TZ). */
export function TurnoverTable({ rows, ctx, filters, onBranch, className }: { rows: HrBranchOut[]; ctx: ExportContext; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('kad.turn.title');
  const headers = [t('kad.br.branch'), t('kad.turn.hired'), t('kad.turn.fired'), t('kad.turn.rate'), t('kad.turn.fact')];
  const columns: Column<HrBranchOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (b) => b.name, sortValue: (b) => b.name, wrap: true },
    { key: 'hired', header: headers[1] ?? '', cell: (b) => (b.hired === null ? t('kad.suppressed') : formatNumber(b.hired)), sortValue: (b) => b.hired, align: 'right' },
    { key: 'fired', header: headers[2] ?? '', cell: (b) => (b.fired === null ? t('kad.suppressed') : formatNumber(b.fired)), sortValue: (b) => b.fired, align: 'right' },
    {
      key: 'rate',
      header: headers[3] ?? '',
      cell: (b) => (
        <span className={cx('exec', b.turnover !== null && b.turnover > TURN_HIGH && 'neg')}>
          {formatPct(b.turnover, 1)}
          <i aria-hidden="true">
            <b style={{ width: `${Math.min(100, Math.max(0, (b.turnover ?? 0) * 300))}%` }} />
          </i>
        </span>
      ),
      sortValue: (b) => b.turnover,
      align: 'right',
    },
    { key: 'fact', header: headers[4] ?? '', cell: (b) => formatNumber(b.fact), sortValue: (b) => b.fact, align: 'right' },
  ];
  return (
    <Card className={className} title={title} sub={t('kad.turn.sub')} exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((b) => [b.name, b.hired, b.fired, b.turnover === null ? null : Math.round(b.turnover * 1000) / 10, b.fact]) })} />}>
      <div title={formula('staffTurnover')}>
        <Table caption={title} columns={columns} rows={rows} rowKey={(b) => b.branch_id} onRowClick={(b) => toggleBranch(filters, b.branch_id, onBranch)} free />
      </div>
    </Card>
  );
}
