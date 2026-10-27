import type { InvRiskiOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { InvKpis } from './parts/InvKpis';
import { NoObjects } from './parts/NoObjects';
import { AdvancesCard, GapsCard, LaggingCard, StagesCard } from './parts/RiskCards';

export default function InvesticiiRiski({ filters, onBranch }: SectionPageProps) {
  const query = useSection<InvRiskiOut>('/investicii/riski', filters);
  return (
    <SectionData query={query}>
      {(data) =>
        data.kpis.has_objects ? (
          <>
            <InvKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <LaggingCard className="c6" rows={data.lagging} filters={filters} onBranch={onBranch} />
              <GapsCard className="c6" rows={data.gaps} filters={filters} onBranch={onBranch} />
              <StagesCard className="c7" stages={data.stages} />
              <AdvancesCard className="c5" rows={data.advances} />
            </div>
          </>
        ) : (
          <NoObjects />
        )
      }
    </SectionData>
  );
}
