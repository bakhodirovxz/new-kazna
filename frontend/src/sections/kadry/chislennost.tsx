import type { KadryChislennostOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { CategoriesCard } from './parts/CategoriesCard';
import { HrBranchesTable } from './parts/HrBranchesTable';
import { HrKpis } from './parts/HrKpis';
import { VacancyRank } from './parts/HrRanks';
import { NoStaff } from './parts/NoStaff';

export default function KadryChislennost({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KadryChislennostOut>('/kadry/chislennost', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <HrKpis kpis={data.kpis} />
          {data.kpis.has_data ? null : <NoStaff />}
          <div className="grid">
            <HrBranchesTable className="c12" rows={data.branches} kpis={data.kpis} ctx={ctx} filters={filters} onBranch={onBranch} />
            <CategoriesCard className="c6" categories={data.categories} />
            <VacancyRank className="c6" rows={data.branches} filters={filters} onBranch={onBranch} />
          </div>
        </>
      )}
    </SectionData>
  );
}
