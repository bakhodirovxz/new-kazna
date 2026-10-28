import type { SectionPageProps } from '../registry';
import { CashFlowCard, DscrChartCard } from './parts/charts';
import { FinmodelFrame } from './parts/FinmodelFrame';
import { DebtTable } from './parts/tables';

export default function FinDolg({ section, page, filters }: SectionPageProps) {
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <FinmodelFrame filters={filters}>
      {(model) => (
        <div className="grid">
          <DscrChartCard className="c6" years={model.years} covenant={model.base.covenant} ctx={ctx} />
          <CashFlowCard className="c6" years={model.years} ctx={ctx} />
          <DebtTable className="c12" years={model.years} covenant={model.base.covenant} />
        </div>
      )}
    </FinmodelFrame>
  );
}
