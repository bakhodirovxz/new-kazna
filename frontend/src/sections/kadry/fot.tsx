import type { KadryFotOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { FotCard } from './parts/FotCard';
import { HrKpis } from './parts/HrKpis';
import { AvgSalaryRank, PayrollRank, PayrollShareCard } from './parts/HrRanks';

export default function KadryFot({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KadryFotOut>('/kadry/fot', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <HrKpis kpis={data.kpis} />
          <div className="grid">
            <FotCard className="c8" months={data.months} ctx={ctx} />
            <PayrollShareCard className="c4" kpis={data.kpis} />
            <AvgSalaryRank className="c6" rows={data.branches} filters={filters} onBranch={onBranch} />
            <PayrollRank className="c6" rows={data.branches} filters={filters} onBranch={onBranch} />
          </div>
        </>
      )}
    </SectionData>
  );
}
