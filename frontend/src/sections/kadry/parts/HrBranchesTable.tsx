import type { HrBranchOut, HrKpisOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { cx } from '../../../ui/cx';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

const LOW_FILL = 0.9; // prototip: укомплектованность < 90% — qizil

function mln(value: number | null): string {
  return value === null ? t('dash.noValue') : t('kad.money.mln', { value: formatNumber(value, 1) });
}

function Fill({ value }: { value: number | null }) {
  return (
    <span className={cx('exec', value !== null && value < LOW_FILL && 'neg')}>
      {formatPct(value, 0)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, Math.max(0, (value ?? 0) * 100))}%` }} />
      </i>
    </span>
  );
}

export interface HrBranchesTableProps {
  rows: HrBranchOut[];
  kpis: HrKpisOut;
  ctx: ExportContext;
  filters: FilterState;
  onBranch(br: number | null): void;
  className?: string;
}

/** Prototip `hrTable`: штат, факт, вакансии, укомплектованность, ФОТ, средняя зарплата; «Итого». */
export function HrBranchesTable({ rows, kpis, ctx, filters, onBranch, className }: HrBranchesTableProps) {
  const title = t('kad.br.title');
  const headers = [t('kad.br.branch'), t('kad.br.plan'), t('kad.br.fact'), t('kad.br.vac'), t('kad.br.fill'), t('kad.br.payroll'), t('kad.br.avg')];
  const columns: Column<HrBranchOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (b) => b.name, sortValue: (b) => b.name, wrap: true },
    { key: 'plan', header: headers[1] ?? '', cell: (b) => formatNumber(b.plan), sortValue: (b) => b.plan, align: 'right' },
    { key: 'fact', header: headers[2] ?? '', cell: (b) => <b>{formatNumber(b.fact)}</b>, sortValue: (b) => b.fact, align: 'right' },
    { key: 'vac', header: headers[3] ?? '', cell: (b) => <span className={b.fill !== null && b.fill < LOW_FILL ? 'neg' : undefined}>{b.vacancies === null ? t('dash.noValue') : formatNumber(b.vacancies)}</span>, sortValue: (b) => b.vacancies, align: 'right' },
    { key: 'fill', header: headers[4] ?? '', cell: (b) => <Fill value={b.fill} />, sortValue: (b) => b.fill, align: 'right' },
    { key: 'payroll', header: headers[5] ?? '', cell: (b) => formatMoney(b.payroll), sortValue: (b) => b.payroll, align: 'right' },
    { key: 'avg', header: headers[6] ?? '', cell: (b) => mln(b.avg_salary), sortValue: (b) => b.avg_salary, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('kad.br.sub')}
      exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((b) => [b.name, b.plan, b.fact, b.vacancies, b.fill === null ? null : Math.round(b.fill * 1000) / 10, b.payroll, b.avg_salary]) })} />}
    >
      <Table
        caption={title}
        columns={columns}
        rows={rows}
        rowKey={(b) => b.branch_id}
        onRowClick={(b) => toggleBranch(filters, b.branch_id, onBranch)}
        free
        footer={
          <tr>
            <td>{t('kad.br.total')}</td>
            <td>{formatNumber(kpis.plan)}</td>
            <td>{formatNumber(kpis.fact)}</td>
            <td>{kpis.vacancies === null ? t('dash.noValue') : formatNumber(kpis.vacancies)}</td>
            <td>{formatPct(kpis.fill, 0)}</td>
            <td>{formatMoney(kpis.payroll)}</td>
            <td>{mln(kpis.avg_salary)}</td>
          </tr>
        }
      />
    </Card>
  );
}
