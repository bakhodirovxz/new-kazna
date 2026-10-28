import type { KadrySvodOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { CategoriesCard } from './parts/CategoriesCard';
import { FotCard } from './parts/FotCard';
import { HrBranchesTable } from './parts/HrBranchesTable';
import { HrKpis } from './parts/HrKpis';
import { NoStaff } from './parts/NoStaff';
import { Yavka } from './parts/Yavka';

export default function KadrySvod({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KadrySvodOut>('/kadry/svod', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <HrKpis kpis={data.kpis} />
          {data.kpis.has_data ? null : <NoStaff />}
          <div className="grid">
            <Yavka filters={filters} ctx={ctx} onBranch={onBranch} />
            <FotCard className="c8" months={data.months} ctx={ctx} />
            <CategoriesCard className="c4" categories={data.categories} />
            <HrBranchesTable className="c12" rows={data.branches} kpis={data.kpis} ctx={ctx} filters={filters} onBranch={onBranch} />
          </div>
        </>
      )}
    </SectionData>
  );
}
