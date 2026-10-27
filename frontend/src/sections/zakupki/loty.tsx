import type { ZakLotyOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { LotsTable } from './parts/LotsTable';
import { ZakKpis } from './parts/ZakKpis';

export default function ZakupkiLoty({ section, page, filters }: SectionPageProps) {
  const query = useSection<ZakLotyOut>('/zakupki/loty', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <ZakKpis kpis={data.kpis} />
          <div className="grid">
            <LotsTable className="c12" lots={data.lots} ctx={ctx} filters={filters} truncated={data.truncated} />
          </div>
        </>
      )}
    </SectionData>
  );
}
