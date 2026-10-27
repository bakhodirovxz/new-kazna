import type { HrKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

const VAC_HIGH = 0.1; // TZ 4 qoidasi «Вакансии > 10% штата»
const TURN_HIGH = 0.08; // TZ 4 qoidasi «Текучесть > 8%»

function num(value: number | null, digits = 0): string {
  return value === null ? t('dash.noValue') : formatNumber(value, digits);
}

/** Prototip `kpisHr`: штат, факт, вакансии, ФОТ, средняя зарплата, текучесть. Faqat agregatlar. */
export function HrKpis({ kpis }: { kpis: HrKpisOut }) {
  const payroll = moneyParts(kpis.payroll);
  const staff = kpis.has_data;
  return (
    <KpiGrid>
      <KpiTile icon="people" label={t('kad.kpi.plan')} value={staff ? num(kpis.plan) : t('dash.noValue')} unit={t('unit.peopleShort')} delta={staff ? t('kad.kpi.planNote') : t('kad.kpi.noStaff')} hint={formula('headcount')} />
      <KpiTile icon="people" label={t('kad.kpi.fact')} value={staff ? num(kpis.fact) : t('dash.noValue')} unit={t('unit.peopleShort')} delta={staff ? t('kad.kpi.factNote', { pct: formatPct(kpis.fill, 1) }) : t('kad.kpi.noStaff')} hint={formula('headcount')} />
      <KpiTile
        icon="alert"
        label={t('kad.kpi.vacancies')}
        value={<span className={kpis.vacancy_share !== null && kpis.vacancy_share > VAC_HIGH ? 'neg' : undefined}>{num(kpis.vacancies)}</span>}
        delta={t('kad.kpi.vacanciesNote', { pct: formatPct(kpis.vacancy_share, 1) })}
        hint={formula('vacancies')}
      />
      <KpiTile icon="coins" label={t('kad.kpi.payroll')} value={payroll.value} unit={payroll.unit} delta={t('kad.kpi.payrollNote', { pct: formatPct(kpis.payroll_share, 1) })} hint={formula('payroll')} />
      <KpiTile icon="card" label={t('kad.kpi.avg')} value={num(kpis.avg_salary, 1)} unit={t('kad.kpi.avgUnit')} delta={t('kad.kpi.avgNote')} hint={formula('avgSalary')} />
      <KpiTile
        icon="net"
        label={t('kad.kpi.turnover')}
        value={<span className={kpis.turnover !== null && kpis.turnover > TURN_HIGH ? 'neg' : undefined}>{formatPct(kpis.turnover, 1)}</span>}
        delta={t('kad.kpi.turnoverNote', { hired: kpis.hired, fired: kpis.fired })}
        hint={formula('staffTurnover')}
      />
    </KpiGrid>
  );
}
