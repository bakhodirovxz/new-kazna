import type { StockPositionOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { NoData } from '../../../dash/DataState';
import type { ExportContext } from '../../../dash/exportLog';
import { formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { buildHash } from '../../../router/hash';
import { Card } from '../../../ui/Card';
import { cx } from '../../../ui/cx';
import { Table, type Column } from '../../../ui/Table';

function qty(value: number | null, unit: string): string {
  return value === null ? t('dash.noValue') : `${formatNumber(value, 0)} ${unit}`;
}

function Coverage({ value }: { value: number | null }) {
  return (
    <span className={cx('exec', value !== null && value < 0.5 && 'neg')}>
      {formatPct(value, 0)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, Math.max(0, (value ?? 0) * 100))}%` }} />
      </i>
    </span>
  );
}

export interface BelowMinCardProps {
  rows: StockPositionOut[];
  hasMinimum: boolean;
  title: string;
  sub: string;
  ctx: ExportContext;
  more?: boolean;
  className?: string;
}

/** Prototip `belowTable`: позиции ниже минимума с обеспеченностью (< 50% — qizil); tartib serverdan. */
export function BelowMinCard({ rows, hasMinimum, title, sub, ctx, more = false, className }: BelowMinCardProps) {
  const headers = [t('sklad.col.position'), t('sklad.col.warehouse'), t('sklad.col.qty'), t('sklad.col.min'), t('sklad.col.coverage')];
  const columns: Column<StockPositionOut>[] = [
    {
      key: 'name',
      header: headers[0] ?? '',
      cell: (p) => (
        <>
          {p.name}
          <br />
          <span className="note">{p.category}</span>
        </>
      ),
      sortValue: (p) => p.name,
      wrap: true,
    },
    {
      key: 'warehouse',
      header: headers[1] ?? '',
      cell: (p) => (
        <>
          {p.branch_name}
          <br />
          <span className="note">{p.warehouse}</span>
        </>
      ),
      sortValue: (p) => p.branch_name,
      wrap: true,
    },
    { key: 'qty', header: headers[2] ?? '', cell: (p) => qty(p.qty, p.unit), sortValue: (p) => p.qty, align: 'right' },
    { key: 'min', header: headers[3] ?? '', cell: (p) => qty(p.min_qty, p.unit), sortValue: (p) => p.min_qty, align: 'right' },
    { key: 'coverage', header: headers[4] ?? '', cell: (p) => <Coverage value={p.coverage} />, sortValue: (p) => p.coverage, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={sub}
      exportSlot={
        hasMinimum && rows.length ? (
          <CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((p) => [p.name, p.warehouse, p.qty, p.min_qty, p.coverage === null ? null : Math.round(p.coverage * 100)]) })} />
        ) : undefined
      }
    >
      {hasMinimum ? (
        <Table caption={title} columns={columns} rows={rows} rowKey={(p) => `${p.branch_id}-${p.nom_code}-${p.warehouse}`} free empty={<p className="note">{t('sklad.below.none')}</p>} />
      ) : (
        <NoData kind="source" source={t('sklad.below.source')} />
      )}
      {more ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'sklad', page: 'minimum', br: ctx.br, per: ctx.per })}>
          {t('sklad.below.all')}
        </a>
      ) : null}
    </Card>
  );
}
