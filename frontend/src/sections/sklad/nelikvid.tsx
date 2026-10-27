import type { SkladNelikvidOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { AgesCard } from './parts/AgesCard';
import { IlliquidCard } from './parts/IlliquidCard';
import { StockKpis } from './parts/StockKpis';

export default function SkladNelikvid({ section, page, filters }: SectionPageProps) {
  const query = useSection<SkladNelikvidOut>('/sklad/nelikvid', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <StockKpis kpis={data.kpis} />
          <div className="grid">
            <AgesCard className="c4" ages={data.ages} hasAge={data.kpis.has_age} />
            <IlliquidCard className="c8" rows={data.illiquid} hasAge={data.kpis.has_age} ctx={ctx} />
          </div>
        </>
      )}
    </SectionData>
  );
}
