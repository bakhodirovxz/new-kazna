import type { SkladMinimumOut } from '../../api/types';
import { t } from '../../i18n';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { BelowMinCard } from './parts/BelowMinCard';
import { StockKpis } from './parts/StockKpis';

export default function SkladMinimum({ section, page, filters }: SectionPageProps) {
  const query = useSection<SkladMinimumOut>('/sklad/minimum', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <StockKpis kpis={data.kpis} />
          <div className="grid">
            <BelowMinCard className="c12" rows={data.below} hasMinimum={data.kpis.has_minimum} title={t('sklad.below.title')} sub={t('sklad.below.subAll')} ctx={ctx} />
          </div>
        </>
      )}
    </SectionData>
  );
}
