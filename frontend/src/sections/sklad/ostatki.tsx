import type { SkladOstatkiOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { CategoriesCard } from './parts/CategoriesCard';
import { StockBranchesTable } from './parts/StockBranchesTable';
import { StockKpis } from './parts/StockKpis';

export default function SkladOstatki({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<SkladOstatkiOut>('/sklad/ostatki', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <StockKpis kpis={data.kpis} />
          <div className="grid">
            <StockBranchesTable className="c8" rows={data.branches} ctx={ctx} filters={filters} onBranch={onBranch} />
            <CategoriesCard className="c4" categories={data.categories} asOf={data.kpis.as_of} />
          </div>
        </>
      )}
    </SectionData>
  );
}
