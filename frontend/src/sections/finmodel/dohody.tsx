import type { SectionPageProps } from '../registry';
import { StructureCard } from './parts/charts';
import { FinmodelFrame } from './parts/FinmodelFrame';
import { CostTariffTable } from './parts/tables';

export default function FinDohody({ section, page, filters }: SectionPageProps) {
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <FinmodelFrame filters={filters}>
      {(model) => (
        <div className="grid">
          <StructureCard className="c7" years={model.years} ctx={ctx} />
          <CostTariffTable className="c5" years={model.years} />
        </div>
      )}
    </FinmodelFrame>
  );
}
