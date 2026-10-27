import type { PlanFactRowOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { buildHash } from '../../../router/hash';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';

function Exec({ value }: { value: number | null }) {
  return (
    <span className="exec">
      {formatPct(value, 0)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, (value ?? 0) * 100)}%` }} />
      </i>
    </span>
  );
}

function Deviation({ value }: { value: number }) {
  // TZ 4: план − факт; перерасход (факт > план) — отрицательное отклонение, красным.
  return <span className={value < 0 ? 'neg' : undefined}>{formatMoney(value)}</span>;
}

export function PlanFactCard({ rows, limit, onItem, ctx, className }: { rows: PlanFactRowOut[]; limit?: number; onItem(id: number): void; ctx: ExportContext; className?: string }) {
  const shown = limit ? rows.slice(0, limit) : rows;
  const plan = rows.reduce((s, r) => s + r.plan, 0);
  const fact = rows.reduce((s, r) => s + r.fact, 0);
  const title = t('kazna.planFact.title');
  const columns: Column<PlanFactRowOut>[] = [
    { key: 'name', header: t('dash.item'), cell: (r) => r.name, sortValue: (r) => r.name, wrap: true, align: 'left' },
    { key: 'plan', header: t('dash.plan'), cell: (r) => formatMoney(r.plan), sortValue: (r) => r.plan, align: 'right' },
    { key: 'fact', header: t('dash.fact'), cell: (r) => formatMoney(r.fact), sortValue: (r) => r.fact, align: 'right' },
    { key: 'exec', header: t('kazna.planFact.execution'), cell: (r) => <Exec value={r.execution} />, sortValue: (r) => r.execution, align: 'right' },
    { key: 'dev', header: t('kazna.planFact.deviation'), cell: (r) => <Deviation value={r.deviation} />, sortValue: (r) => r.deviation, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={limit ? t('kazna.planFact.subTop', { count: limit }) : t('kazna.planFact.sub')}
      exportSlot={
        <CardExport
          title={title}
          ctx={ctx}
          csv={() => ({ headers: [t('dash.item'), t('dash.plan'), t('dash.fact'), `${t('kazna.planFact.execution')}, %`, t('kazna.planFact.deviation')], rows: rows.map((r) => [r.name, r.plan, r.fact, r.execution === null ? null : Math.round(r.execution * 1000) / 10, r.deviation]) })}
        />
      }
    >
      <Table
        caption={title}
        columns={columns}
        rows={shown}
        rowKey={(r) => r.item_id}
        onRowClick={(r) => onItem(r.item_id)}
        free
        bare
        footer={
          <tr>
            <td className="l">{t('kazna.planFact.total')}</td>
            <td data-label={t('dash.plan')}>{formatMoney(plan)}</td>
            <td data-label={t('dash.fact')}>{formatMoney(fact)}</td>
            <td data-label={t('kazna.planFact.execution')}>
              <Exec value={plan ? fact / plan : null} />
            </td>
            <td data-label={t('kazna.planFact.deviation')}>
              <Deviation value={plan - fact} />
            </td>
          </tr>
        }
      />
      {limit ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'kazna', page: 'platezhi', br: ctx.br, per: ctx.per })}>
          {t('kazna.planFact.all')}
        </a>
      ) : null}
    </Card>
  );
}
