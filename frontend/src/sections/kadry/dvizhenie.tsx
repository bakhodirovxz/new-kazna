import type { KadryDvizhenieOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { HrKpis } from './parts/HrKpis';
import { OvertimeCard } from './parts/HrRanks';
import { MovesCard } from './parts/MovesCard';
import { NoStaff } from './parts/NoStaff';
import { TurnoverTable } from './parts/TurnoverTable';

export default function KadryDvizhenie({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KadryDvizhenieOut>('/kadry/dvizhenie', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <HrKpis kpis={data.kpis} />
          {data.kpis.has_data ? null : <NoStaff />}
          <div className="grid">
            <MovesCard className="c8" months={data.months} ctx={ctx} />
            <OvertimeCard className="c4" kpis={data.kpis} rows={data.branches} filters={filters} onBranch={onBranch} />
            <TurnoverTable className="c12" rows={data.branches} ctx={ctx} filters={filters} onBranch={onBranch} />
          </div>
        </>
      )}
    </SectionData>
  );
}
