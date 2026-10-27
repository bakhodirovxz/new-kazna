import type { InvObektyOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { InvKpis } from './parts/InvKpis';
import { NoObjects } from './parts/NoObjects';
import { ObjectsTable } from './parts/ObjectsTable';

export default function InvesticiiObekty({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<InvObektyOut>('/investicii/obekty', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.kpis.has_objects ? (
          <>
            <InvKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <ObjectsTable className="c12" objects={data.objects} ctx={ctx} filters={filters} onBranch={onBranch} />
            </div>
          </>
        ) : (
          <NoObjects />
        )
      }
    </SectionData>
  );
}
