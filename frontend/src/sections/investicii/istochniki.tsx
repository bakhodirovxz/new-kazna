import type { InvIstochnikiOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { CumCard } from './parts/CumCard';
import { InvKpis } from './parts/InvKpis';
import { NoObjects } from './parts/NoObjects';
import { ObjectsRank } from './parts/ObjectsRank';
import { SourcesCard } from './parts/SourcesCard';

export default function InvesticiiIstochniki({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<InvIstochnikiOut>('/investicii/istochniki', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.kpis.has_objects ? (
          <>
            <InvKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <SourcesCard className="c5" sources={data.sources} />
              <ObjectsRank className="c7" objects={data.objects} filters={filters} onBranch={onBranch} />
              <CumCard className="c12" points={data.cumulative} ctx={ctx} />
            </div>
          </>
        ) : (
          <NoObjects />
        )
      }
    </SectionData>
  );
}
