import type { ProizvRealizOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { NoStations } from './parts/NoStations';
import { PaymentRank } from './parts/PaymentRank';
import { ProdKpis } from './parts/ProdKpis';
import { SalesMonthsCard } from './parts/SalesMonthsCard';

export default function ProizvodstvoRealiz({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ProizvRealizOut>('/proizvodstvo/realiz', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_stations ? (
          <>
            <ProdKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <SalesMonthsCard className="c8" months={data.months} ctx={ctx} />
              <PaymentRank className="c4" stations={data.stations} filters={filters} onBranch={onBranch} />
            </div>
          </>
        ) : (
          <NoStations />
        )
      }
    </SectionData>
  );
}
