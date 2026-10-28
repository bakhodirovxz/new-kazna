import type { SectionPageProps } from '../registry';
import { FinmodelFrame } from './parts/FinmodelFrame';
import { SensitivityCard } from './parts/SensitivityCard';
import { ScenarioTable } from './parts/tables';

export default function FinScenarii({ filters }: SectionPageProps) {
  return (
    <FinmodelFrame filters={filters}>
      {(model) => (
        <div className="grid">
          <ScenarioTable className="c12" model={model} />
          <SensitivityCard className="c12" model={model} />
        </div>
      )}
    </FinmodelFrame>
  );
}
