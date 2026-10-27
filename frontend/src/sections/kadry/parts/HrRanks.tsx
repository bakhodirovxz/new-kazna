import type { HrBranchOut, HrKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import { formatHours, formatPeople } from '../../../dash/people';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { toggleBranch } from '../../useSection';

interface RankProps {
  rows: HrBranchOut[];
  filters: FilterState;
  onBranch(br: number | null): void;
  className?: string;
}

/** Prototip «Вакансии по филиалам»: незанятые штатные единицы. */
export function VacancyRank({ rows, filters, onBranch, className }: RankProps) {
  const title = t('kad.vac.title');
  const items = rows
    .filter((b) => (b.vacancies ?? 0) > 0)
    .sort((a, b) => (b.vacancies ?? 0) - (a.vacancies ?? 0))
    .map((b) => ({ id: b.branch_id, name: b.name, value: b.vacancies ?? 0, note: t('kad.vac.note', { pct: formatPct(b.fill === null ? null : 1 - b.fill, 1) }) }));
  return (
    <Card className={className} title={title} sub={t('kad.vac.sub')}>
      <div title={formula('vacancies')}>
        <Rank label={title} items={items} format={(v) => formatPeople(v)} onSelect={(id) => toggleBranch(filters, Number(id), onBranch)} activeId={filters.br} />
      </div>
    </Card>
  );
}

/** Prototip «Средняя зарплата по филиалам» (млн сум в месяц). */
export function AvgSalaryRank({ rows, filters, onBranch, className }: RankProps) {
  const title = t('kad.avg.title');
  const items = rows
    .filter((b) => b.avg_salary !== null)
    .sort((a, b) => (b.avg_salary ?? 0) - (a.avg_salary ?? 0))
    .map((b) => ({ id: b.branch_id, name: b.name, value: b.avg_salary ?? 0, note: formatPeople(b.fact) }));
  return (
    <Card className={className} title={title} sub={t('kad.avg.sub')}>
      <div title={formula('avgSalary')}>
        <Rank label={title} items={items} format={(v) => t('kad.money.mln', { value: formatNumber(v, 1) })} onSelect={(id) => toggleBranch(filters, Number(id), onBranch)} activeId={filters.br} />
      </div>
    </Card>
  );
}

/** Prototip «ФОТ по филиалам»: выплаты за период. */
export function PayrollRank({ rows, filters, onBranch, className }: RankProps) {
  const title = t('kad.pay.title');
  const items = rows
    .filter((b) => b.payroll !== null)
    .sort((a, b) => (b.payroll ?? 0) - (a.payroll ?? 0))
    .map((b) => ({ id: b.branch_id, name: b.name, value: b.payroll ?? 0 }));
  return (
    <Card className={className} title={title} sub={t('kad.pay.sub')}>
      <Rank label={title} items={items} onSelect={(id) => toggleBranch(filters, Number(id), onBranch)} activeId={filters.br} />
    </Card>
  );
}

/** Prototip «Доля ФОТ в расходовании». */
export function PayrollShareCard({ kpis, className }: { kpis: HrKpisOut; className?: string }) {
  const share = kpis.payroll_share;
  return (
    <Card className={className} title={t('kad.share.title')} sub={t('kad.share.sub')}>
      <div className="bigline" title={formula('payroll')}>
        <b>{formatPct(share, 1)}</b>
        <span>{t('kad.share.of', { payroll: formatMoney(kpis.payroll), total: formatMoney(kpis.outflow) })}</span>
      </div>
      <div className="prog__t" aria-hidden="true">
        <i style={{ width: `${Math.min(100, Math.max(0, (share ?? 0) * 100))}%` }} />
      </div>
    </Card>
  );
}

/** Prototip «Сверхурочные часы»: всего и на работника, по филиалам. */
export function OvertimeCard({ kpis, rows, filters, onBranch, className }: RankProps & { kpis: HrKpisOut }) {
  const title = t('kad.ot.title');
  const items = rows
    .filter((b) => (b.overtime ?? 0) > 0)
    .sort((a, b) => (b.overtime ?? 0) - (a.overtime ?? 0))
    .map((b) => ({ id: b.branch_id, name: b.name, value: b.overtime ?? 0, note: t('kad.ot.perBranch', { hours: formatNumber(b.overtime_per_employee ?? 0, 1) }) }));
  return (
    <Card className={className} title={title} sub={t('kad.ot.sub')}>
      <div className="bigline" title={formula('overtime')}>
        <b>{formatHours(kpis.overtime)}</b>
        <span>{t('kad.ot.per', { hours: formatNumber(kpis.overtime_per_employee ?? 0, 1) })}</span>
      </div>
      <Rank label={title} items={items} format={(v) => formatHours(v)} onSelect={(id) => toggleBranch(filters, Number(id), onBranch)} activeId={filters.br} />
    </Card>
  );
}
