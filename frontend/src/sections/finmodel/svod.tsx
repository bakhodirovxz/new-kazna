import type { SectionPageProps } from '../registry';
import { BaseInfoCard } from './parts/BaseInfoCard';
import { CashFlowCard, RevenueCard } from './parts/charts';
import { FinmodelFrame } from './parts/FinmodelFrame';
import { ModelTable } from './parts/tables';

export default function FinSvod({ section, page, filters }: SectionPageProps) {
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <FinmodelFrame filters={filters}>
      {(model) => (
        <div className="grid">
          <RevenueCard className="c6" years={model.years} ctx={ctx} />
          <CashFlowCard className="c6" years={model.years} ctx={ctx} />
          <ModelTable className="c8" model={model} ctx={ctx} />
          <BaseInfoCard className="c4" base={model.base} />
        </div>
      )}
    </FinmodelFrame>
  );
}
