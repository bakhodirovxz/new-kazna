import type { StockPositionOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { NoData } from '../../../dash/DataState';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';

/** Prototip `idleTable`: без движения более 180 дней, по стоимости; > 365 дней — qizil belgi. */
export function IlliquidCard({ rows, hasAge, ctx, className }: { rows: StockPositionOut[]; hasAge: boolean; ctx: ExportContext; className?: string }) {
  const title = t('sklad.idle.title');
  const headers = [t('sklad.col.position'), t('sklad.col.warehouse'), t('sklad.col.count'), t('sklad.col.value'), t('sklad.col.age')];
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
    { key: 'warehouse', header: headers[1] ?? '', cell: (p) => p.branch_name, sortValue: (p) => p.branch_name, wrap: true },
    { key: 'qty', header: headers[2] ?? '', cell: (p) => `${formatNumber(p.qty, 0)} ${p.unit}`, sortValue: (p) => p.qty, align: 'right' },
    { key: 'value', header: headers[3] ?? '', cell: (p) => <b>{formatMoney(p.value)}</b>, sortValue: (p) => p.value, align: 'right' },
    {
      key: 'age',
      header: headers[4] ?? '',
      cell: (p) => (p.age_days === null ? t('dash.noValue') : <Badge tone={p.age_days > 365 ? 'neg' : 'neutral'}>{t('sklad.col.days', { days: p.age_days })}</Badge>),
      sortValue: (p) => p.age_days,
    },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('sklad.idle.sub')}
      exportSlot={hasAge && rows.length ? <CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((p) => [p.name, p.branch_name, p.qty, p.value, p.age_days]) })} /> : undefined}
    >
      {hasAge ? (
        <Table caption={title} columns={columns} rows={rows} rowKey={(p) => `${p.branch_id}-${p.nom_code}-${p.warehouse}`} free empty={<p className="note">{t('sklad.idle.none')}</p>} />
      ) : (
        <NoData kind="source" source={t('sklad.age.source')} />
      )}
    </Card>
  );
}
