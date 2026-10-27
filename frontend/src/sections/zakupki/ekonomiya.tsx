import type { ZakEkonomiyaOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { AvgDaysCard, CancelledCard, EconomyTable } from './parts/EconomyCards';
import { ZakKpis } from './parts/ZakKpis';

export default function ZakupkiEkonomiya({ section, page, filters }: SectionPageProps) {
  const query = useSection<ZakEkonomiyaOut>('/zakupki/ekonomiya', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <ZakKpis kpis={data.kpis} />
          <div className="grid">
            <EconomyTable className="c12" methods={data.methods} ctx={ctx} />
            <CancelledCard className="c6" lots={data.cancelled} />
            <AvgDaysCard className="c6" kpis={data.kpis} methods={data.methods} />
          </div>
        </>
      )}
    </SectionData>
  );
}
