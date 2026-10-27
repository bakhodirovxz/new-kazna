import { useState } from 'react';
import type { ZakLotOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney } from '../../../dash/money';
import { t, type MessageKey } from '../../../i18n';
import { buildHash } from '../../../router/hash';
import type { FilterState } from '../../../shell/useFilters';
import { Badge, type BadgeTone } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';

type LotFilter = 'all' | 'work' | 'late' | 'done';
const FILTERS: LotFilter[] = ['all', 'work', 'late', 'done'];
const STATUS_KEYS: Record<string, MessageKey> = {
  'объявлен': 'zak.status.announced',
  'на оценке': 'zak.status.evaluation',
  'договор заключён': 'zak.status.done',
  'отменён': 'zak.status.cancelled',
};
const STATUS_TONE: Record<string, BadgeTone> = { work: 'blue', done: 'ok', cancelled: 'neutral' };

export function lotStatusLabel(status: string): string {
  const key = STATUS_KEYS[status];
  return key ? t(key) : status;
}

function matches(lot: ZakLotOut, filter: LotFilter): boolean {
  if (filter === 'work') return lot.kind === 'work';
  if (filter === 'late') return lot.overdue;
  if (filter === 'done') return lot.kind === 'done';
  return true;
}

function Days({ lot }: { lot: ZakLotOut }) {
  if (lot.days === null) return <>—</>;
  if (lot.kind === 'work') {
    return <Badge tone={lot.overdue ? 'neg' : 'neutral'}>{t('zak.col.daysOf', { days: lot.days, norm: lot.norm_days ?? '—' })}</Badge>;
  }
  return <Badge>{t('zak.col.daysDone', { days: lot.days })}</Badge>;
}

export interface LotsTableProps {
  lots: ZakLotOut[];
  ctx: ExportContext;
  filters: FilterState;
  limit?: number;
  truncated?: boolean;
  className?: string;
}

/** Prototip `lotTable`: реестр лотов с фильтром «все, в работе, просроченные, заключённые». */
export function LotsTable({ lots, ctx, filters, limit, truncated, className }: LotsTableProps) {
  const [filter, setFilter] = useState<LotFilter>('all');
  const title = t('zak.lots.title');
  const shown = lots.filter((l) => matches(l, filter)).slice(0, limit ?? lots.length);
  const headers = [t('zak.col.lot'), t('zak.col.subject'), t('zak.col.branch'), t('zak.col.method'), t('zak.col.start'), t('zak.col.contract'), t('zak.col.status'), t('zak.col.days')];
  const columns: Column<ZakLotOut>[] = [
    { key: 'lot', header: headers[0] ?? '', cell: (l) => l.lot_no, sortValue: (l) => l.lot_no },
    { key: 'subject', header: headers[1] ?? '', cell: (l) => l.subject, sortValue: (l) => l.subject, wrap: true },
    { key: 'branch', header: headers[2] ?? '', cell: (l) => l.branch_name, sortValue: (l) => l.branch_name, wrap: true },
    { key: 'method', header: headers[3] ?? '', cell: (l) => l.method_title, sortValue: (l) => l.method_title, wrap: true },
    { key: 'start', header: headers[4] ?? '', cell: (l) => formatMoney(l.start_price), sortValue: (l) => l.start_price, align: 'right' },
    { key: 'contract', header: headers[5] ?? '', cell: (l) => (l.contract_price === null ? '—' : <b>{formatMoney(l.contract_price)}</b>), sortValue: (l) => l.contract_price, align: 'right' },
    { key: 'status', header: headers[6] ?? '', cell: (l) => <Badge tone={STATUS_TONE[l.kind] ?? 'neutral'}>{lotStatusLabel(l.status)}</Badge>, sortValue: (l) => l.status },
    { key: 'days', header: headers[7] ?? '', cell: (l) => <Days lot={l} />, sortValue: (l) => l.days },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('zak.lots.sub')}
      actions={
        <div className="seg" role="group" aria-label={t('zak.lots.filter')}>
          {FILTERS.map((f) => (
            <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {t(`zak.lots.${f}` as MessageKey)}
            </button>
          ))}
        </div>
      }
      exportSlot={
        <CardExport
          title={title}
          ctx={ctx}
          csv={() => ({ headers, rows: shown.map((l) => [l.lot_no, l.subject, l.branch_name, l.method_title, l.start_price, l.contract_price, lotStatusLabel(l.status), l.days]) })}
        />
      }
    >
      {shown.length ? <Table caption={title} columns={columns} rows={shown} rowKey={(l) => `${l.branch_id}:${l.lot_no}`} free={limit !== undefined} /> : <p className="note">{t('zak.lots.none')}</p>}
      {truncated ? <p className="note">{t('zak.lots.truncated')}</p> : null}
      {limit !== undefined ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'zakupki', page: 'loty', br: filters.br, per: filters.per })}>
          {t('zak.lots.more')}
        </a>
      ) : null}
    </Card>
  );
}
