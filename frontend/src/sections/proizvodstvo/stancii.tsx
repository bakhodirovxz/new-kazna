import type { ProizvStanciiOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { NoStations } from './parts/NoStations';
import { ProdKpis } from './parts/ProdKpis';
import { StationsTable } from './parts/StationsTable';

export default function ProizvodstvoStancii({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ProizvStanciiOut>('/proizvodstvo/stancii', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_stations ? (
          <>
            <ProdKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <StationsTable className="c12" stations={data.stations} kpis={data.kpis} ctx={ctx} filters={filters} onBranch={onBranch} />
            </div>
          </>
        ) : (
          <NoStations />
        )
      }
    </SectionData>
  );
}
