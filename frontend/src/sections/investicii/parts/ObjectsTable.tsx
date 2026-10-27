import type { InvObjectOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import '../../../dash/s4.css';
import { t, type MessageKey } from '../../../i18n';
import { buildHash } from '../../../router/hash';
import type { FilterState } from '../../../shell/useFilters';
import { Badge, type BadgeTone } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

const GAP_PP = 20; // TZ 4: «Разрыв финансового и физического выполнения > 20 п.п.»
const TONES: Record<string, BadgeTone> = { risk: 'neg', lag: 'warn', ok: 'blue' };

export function statusLabel(status: string | null): string {
  return status ? t(`inv.status.${status}` as MessageKey) : t('dash.noValue');
}

export function workLabel(workType: string): string {
  return t(`inv.work.${workType}` as MessageKey);
}

export function FinPhys({ o }: { o: InvObjectOut }) {
  const high = o.gap_pp !== null && o.gap_pp > GAP_PP;
  return (
    <div className="fp" title={`${formula('finExec')}. ${formula('physExec')}`}>
      <div className="fp__h">
        <span>{formatPct(o.financial, 0)}</span>
        <span className={high ? 'neg' : undefined}>{t('inv.col.phys', { pct: formatPct(o.physical, 0) })}</span>
      </div>
      <div className="fp__t" aria-hidden="true">
        <i style={{ width: `${Math.min(100, Math.max(0, (o.financial ?? 0) * 100))}%` }} />
        {o.physical !== null ? <u style={{ left: `${Math.min(100, Math.max(0, o.physical * 100))}%` }} /> : null}
      </div>
    </div>
  );
}

export interface ObjectsTableProps {
  objects: InvObjectOut[];
  ctx: ExportContext;
  filters: FilterState;
  onBranch(br: number | null): void;
  limit?: number;
  className?: string;
}

/** Prototip `objTable`: reestr — стоимость, план года, освоено, график (статус), фин./физ. на одной полосе. */
export function ObjectsTable({ objects, ctx, filters, onBranch, limit, className }: ObjectsTableProps) {
  const title = limit ? t('inv.obj.title') : t('inv.obj.titleAll');
  const rows = objects.slice(0, limit ?? objects.length);
  const headers = [t('inv.col.object'), t('inv.col.branch'), t('inv.col.cost'), t('inv.col.plan'), t('inv.col.fact'), t('inv.col.schedule'), t('inv.col.finphys'), t('inv.col.deadline')];
  const columns: Column<InvObjectOut>[] = [
    {
      key: 'name',
      header: headers[0] ?? '',
      cell: (o) => (
        <>
          {o.name}
          <span className="obj-note">{`${o.object_code}, ${workLabel(o.work_type)}, ${o.source_name}`}</span>
        </>
      ),
      sortValue: (o) => o.name,
      wrap: true,
    },
    { key: 'branch', header: headers[1] ?? '', cell: (o) => o.branch_name, sortValue: (o) => o.branch_name, wrap: true },
    { key: 'cost', header: headers[2] ?? '', cell: (o) => formatMoney(o.total_cost), sortValue: (o) => o.total_cost, align: 'right' },
    { key: 'plan', header: headers[3] ?? '', cell: (o) => formatMoney(o.plan_year), sortValue: (o) => o.plan_year, align: 'right' },
    { key: 'fact', header: headers[4] ?? '', cell: (o) => <b>{formatMoney(o.fact_ytd)}</b>, sortValue: (o) => o.fact_ytd, align: 'right' },
    {
      key: 'schedule',
      header: headers[5] ?? '',
      cell: (o) => <Badge tone={TONES[o.status ?? ''] ?? 'neutral'}>{`${formatPct(o.execution, 0)}, ${statusLabel(o.status)}`}</Badge>,
      sortValue: (o) => o.execution,
    },
    { key: 'fp', header: headers[6] ?? '', cell: (o) => <FinPhys o={o} />, sortValue: (o) => o.gap_pp },
    { key: 'deadline', header: headers[7] ?? '', cell: (o) => (o.commissioning_year === null ? '—' : String(o.commissioning_year)), sortValue: (o) => o.commissioning_year, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={limit ? t('inv.obj.sub') : t('inv.obj.subAll')}
      exportSlot={
        <CardExport
          title={title}
          ctx={ctx}
          csv={() => ({
            headers,
            rows: objects.map((o) => [o.name, o.branch_name, o.total_cost, o.plan_year, o.fact_ytd, o.execution === null ? null : Math.round(o.execution * 1000) / 10, o.financial === null ? null : Math.round(o.financial * 1000) / 10, o.commissioning_year]),
          })}
        />
      }
    >
      <div title={formula('objStatus')}>
        <Table caption={title} columns={columns} rows={rows} rowKey={(o) => o.object_id} onRowClick={(o) => toggleBranch(filters, o.branch_id, onBranch)} free={limit !== undefined} />
      </div>
      {limit !== undefined ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'investicii', page: 'obekty', br: filters.br, per: filters.per })}>
          {t('inv.obj.more')}
        </a>
      ) : null}
    </Card>
  );
}
