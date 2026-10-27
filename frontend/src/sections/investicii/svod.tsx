import type { InvSvodOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { CumCard } from './parts/CumCard';
import { InvKpis } from './parts/InvKpis';
import { NoObjects } from './parts/NoObjects';
import { ObjectsTable } from './parts/ObjectsTable';
import { SourcesCard } from './parts/SourcesCard';

export default function InvesticiiSvod({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<InvSvodOut>('/investicii/svod', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.kpis.has_objects ? (
          <>
            <InvKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <CumCard className="c8" points={data.cumulative} ctx={ctx} />
              <SourcesCard className="c4" sources={data.sources} />
              <ObjectsTable className="c12" objects={data.objects} ctx={ctx} filters={filters} onBranch={onBranch} limit={6} />
            </div>
          </>
        ) : (
          <NoObjects />
        )
      }
    </SectionData>
  );
}
