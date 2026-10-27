import type { KaznaCelevyeOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { FundsByBranch, FundsBySource } from './parts/FundsCards';

export default function KaznaCelevye({ filters, onBranch }: SectionPageProps) {
  const query = useSection<KaznaCelevyeOut>('/kazna/celevye', filters);
  return (
    <SectionData query={query}>
      {(data) => (
        <div className="grid">
          <FundsBySource className="c6" rows={data.sources} date={data.period.date_to} />
          <FundsByBranch className="c6" rows={data.branches} filters={filters} onBranch={onBranch} />
        </div>
      )}
    </SectionData>
  );
}
