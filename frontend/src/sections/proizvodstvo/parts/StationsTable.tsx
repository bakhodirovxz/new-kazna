import type { ProdKpisOut, StationGenOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { formatKwh } from '../../../dash/energy';
import type { ExportContext } from '../../../dash/exportLog';
import { formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { cx } from '../../../ui/cx';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

function Exec({ value }: { value: number | null }) {
  const low = value !== null && value < 0.95;
  return (
    <span className={cx('exec', low && 'neg')}>
      {formatPct(value, 0)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, Math.max(0, (value ?? 0) * 100))}%` }} />
      </i>
    </span>
  );
}

export interface StationsTableProps {
  stations: StationGenOut[];
  kpis: ProdKpisOut;
  ctx: ExportContext;
  filters: FilterState;
  onBranch(br: number | null): void;
  className?: string;
}

/** Prototip `stTable` (TZ 5 «таблица станций с КИУМ»): quvvat, reja, fakt, bajarilish, КИУМ, отпуск. */
export function StationsTable({ stations, kpis, ctx, filters, onBranch, className }: StationsTableProps) {
  const title = t('proizv.table.title');
  const headers = [
    t('proizv.table.station'), t('proizv.table.capacity'), t('proizv.table.plan'), t('proizv.table.fact'),
    t('proizv.table.execution'), t('proizv.table.kium'), t('proizv.table.supply'),
  ];
  const columns: Column<StationGenOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (s) => s.name, sortValue: (s) => s.name, wrap: true },
    { key: 'capacity', header: headers[1] ?? '', cell: (s) => formatNumber(s.capacity_mw ?? 0), sortValue: (s) => s.capacity_mw, align: 'right' },
    { key: 'plan', header: headers[2] ?? '', cell: (s) => formatKwh(s.plan), sortValue: (s) => s.plan, align: 'right' },
    { key: 'fact', header: headers[3] ?? '', cell: (s) => <b>{formatKwh(s.generation)}</b>, sortValue: (s) => s.generation, align: 'right' },
    { key: 'execution', header: headers[4] ?? '', cell: (s) => <Exec value={s.execution} />, sortValue: (s) => s.execution, align: 'right' },
    { key: 'kium', header: headers[5] ?? '', cell: (s) => formatPct(s.kium, 1), sortValue: (s) => s.kium, align: 'right' },
    { key: 'supply', header: headers[6] ?? '', cell: (s) => formatKwh(s.supply), sortValue: (s) => s.supply, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('proizv.table.sub')}
      exportSlot={
        <CardExport
          title={title}
          ctx={ctx}
          csv={() => ({
            headers,
            rows: stations.map((s) => [s.name, s.capacity_mw, s.plan, s.generation, s.execution === null ? null : Math.round(s.execution * 1000) / 10, s.kium === null ? null : Math.round(s.kium * 1000) / 10, s.supply]),
          })}
        />
      }
    >
      <Table
        caption={title}
        columns={columns}
        rows={stations}
        rowKey={(s) => s.branch_id}
        onRowClick={(s) => toggleBranch(filters, s.branch_id, onBranch)}
        free
        footer={
          <tr>
            <td>{t('proizv.table.total')}</td>
            <td>{formatNumber(kpis.capacity_mw ?? 0)}</td>
            <td>{formatKwh(kpis.plan)}</td>
            <td>{formatKwh(kpis.generation)}</td>
            <td>{formatPct(kpis.execution, 0)}</td>
            <td>{formatPct(kpis.kium, 1)}</td>
            <td>{formatKwh(kpis.supply)}</td>
          </tr>
        }
      />
    </Card>
  );
}
