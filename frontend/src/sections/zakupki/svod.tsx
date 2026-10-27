import type { ZakSvodOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { LotsTable } from './parts/LotsTable';
import { MethodsCard } from './parts/MethodsCard';
import { ZakKpis } from './parts/ZakKpis';
import { ZakMonthsCard } from './parts/ZakMonthsCard';

export default function ZakupkiSvod({ section, page, filters }: SectionPageProps) {
  const query = useSection<ZakSvodOut>('/zakupki/svod', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <ZakKpis kpis={data.kpis} />
          <div className="grid">
            <ZakMonthsCard className="c8" months={data.months} ctx={ctx} />
            <MethodsCard className="c4" methods={data.methods} />
            <LotsTable className="c12" lots={data.lots} ctx={ctx} filters={filters} limit={8} />
          </div>
        </>
      )}
    </SectionData>
  );
}
