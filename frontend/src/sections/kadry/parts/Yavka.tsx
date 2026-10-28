import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from '../../../api/client';
import type { KadryYavkaOut, YavkaBranchOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { NoData } from '../../../dash/DataState';
import type { ExportContext } from '../../../dash/exportLog';
import { formatPct } from '../../../dash/money';
import { t, type MessageKey } from '../../../i18n';
import { formatDate, formatNumber, formatTime } from '../../../i18n/format';
import { ru } from '../../../i18n/ru';
import type { FilterState } from '../../../shell/useFilters';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { SectionData } from '../../SectionData';
import { toggleBranch } from '../../useSection';

const POLL_MS = 5 * 60 * 1000; // worker 10 daqiqada yangilaydi
const REASON_CODES = new Set(['business_trip', 'sick_leave', 'annual_leave']);

/** Явка: свой запрос (период не нужен, worker обновляет раз в 10 минут). */
export function useYavka(filters: FilterState) {
  return useQuery({
    queryKey: ['section', '/kadry/yavka', filters.br],
    queryFn: ({ signal }) => api<KadryYavkaOut>('/kadry/yavka', { query: { br: filters.br ?? undefined }, signal, background: true }),
    placeholderData: keepPreviousData,
    refetchInterval: POLL_MS,
  });
}

/** Русская подпись известного кода статуса; неизвестный код — подпись из ответа API. */
export function statusLabel(code: string, apiLabel: string): string {
  const key = `kad.att.st.${code}`;
  return Object.hasOwn(ru, key) ? t(key as MessageKey) : apiLabel;
}

const num = (value: number | null): string => (value === null ? t('kad.suppressed') : formatNumber(value));

function Tile({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{num(value)}</dd>
    </div>
  );
}

function Summary({ data }: { data: KadryYavkaOut }) {
  const f = data.totals;
  const rate = f.employees && f.on_work !== null ? f.on_work / f.employees : null;
  const others = data.statuses.filter((s) => s.kind === 'reason' && !REASON_CODES.has(s.code));
  return (
    <>
      <div className="bigline">
        <b>{num(f.on_work)}</b>
        <span>
          {t('kad.att.onWork')}
          {rate === null ? '' : `, ${t('kad.att.rate', { pct: formatPct(rate, 1) })}`}
        </span>
      </div>
      <p className="note">
        {data.generated_at ? t('kad.att.asOf', { time: formatTime(data.generated_at) }) : null}{' '}
        {data.stale ? <Badge tone="neg">{t('kad.att.stale')}</Badge> : null}
      </p>
      <dl className="att">
        <Tile label={t('kad.att.late')} value={f.late} />
        <Tile label={t('kad.att.absent')} value={f.absent} />
        <Tile label={t('kad.att.trip')} value={f.trip} />
        <Tile label={t('kad.att.sick')} value={f.sick} />
        <Tile label={t('kad.att.leave')} value={f.leave} />
        <Tile label={t('kad.att.other')} value={f.other_reason} />
        <Tile label={t('kad.att.rest')} value={f.rest} />
      </dl>
      {others.length ? (
        <ul className="att-others" aria-label={t('kad.att.otherList')}>
          {others.map((s) => (
            <li key={s.code}>
              <span>{statusLabel(s.code, s.label)}</span> <b>{formatNumber(s.employees)}</b>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

function BranchesTable({ rows, ctx, filters, onBranch, className }: { rows: YavkaBranchOut[]; ctx: ExportContext; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('kad.att.brTitle');
  const headers = [t('kad.att.brBranch'), t('kad.att.brHeadcount'), t('kad.att.brOnWork'), t('kad.att.brLate'), t('kad.att.brAbsent'), t('kad.att.brRate')];
  const columns: Column<YavkaBranchOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (b) => b.name, sortValue: (b) => b.name, wrap: true },
    { key: 'employees', header: headers[1] ?? '', cell: (b) => formatNumber(b.employees), sortValue: (b) => b.employees, align: 'right' },
    { key: 'on_work', header: headers[2] ?? '', cell: (b) => <b>{num(b.on_work)}</b>, sortValue: (b) => b.on_work, align: 'right' },
    { key: 'late', header: headers[3] ?? '', cell: (b) => num(b.late), sortValue: (b) => b.late, align: 'right' },
    { key: 'absent', header: headers[4] ?? '', cell: (b) => num(b.absent), sortValue: (b) => b.absent, align: 'right' },
    { key: 'rate', header: headers[5] ?? '', cell: (b) => formatPct(b.attendance_rate, 1), sortValue: (b) => b.attendance_rate, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('kad.att.brSub')}
      exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((b) => [b.name, b.employees, b.on_work, b.late, b.absent, b.attendance_rate === null ? null : Math.round(b.attendance_rate * 1000) / 10]) })} />}
    >
      <Table caption={title} columns={columns} rows={rows} rowKey={(b) => b.branch_id} onRowClick={(b) => toggleBranch(filters, b.branch_id, onBranch)} free />
    </Card>
  );
}

export interface YavkaProps {
  filters: FilterState;
  ctx: ExportContext;
  onBranch(br: number | null): void;
}

/** «Явка сегодня» + таблица по филиалам (в пределах доступных филиалов); пусто — источник не подключён. */
export function Yavka({ filters, ctx, onBranch }: YavkaProps) {
  const query = useYavka(filters);
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_source ? (
          <>
            <Card className="c4" title={t('kad.att.title')} sub={data.date ? t('kad.att.sub', { date: formatDate(data.date) }) : undefined}>
              <Summary data={data} />
            </Card>
            <BranchesTable className="c8" rows={data.branches} ctx={ctx} filters={filters} onBranch={onBranch} />
          </>
        ) : (
          <Card className="c12" title={t('kad.att.title')}>
            <NoData kind="source" source={t('kad.att.source')} />
          </Card>
        )
      }
    </SectionData>
  );
}
