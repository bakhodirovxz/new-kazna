import type { SkladSvodOut } from '../../api/types';
import { NoData } from '../../dash/DataState';
import { t } from '../../i18n';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { BelowMinCard } from './parts/BelowMinCard';
import { CategoriesCard } from './parts/CategoriesCard';
import { StockFlowCard } from './parts/StockFlowCard';
import { StockKpis } from './parts/StockKpis';

export default function SkladSvod({ section, page, filters }: SectionPageProps) {
  const query = useSection<SkladSvodOut>('/sklad/svod', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <StockKpis kpis={data.kpis} />
          {data.kpis.has_data ? null : (
            <Card>
              <NoData kind="period" />
            </Card>
          )}
          <div className="grid">
            <StockFlowCard className="c8" months={data.months} ctx={ctx} />
            <CategoriesCard className="c4" categories={data.categories} asOf={data.kpis.as_of} />
            <BelowMinCard className="c12" rows={data.below} hasMinimum={data.kpis.has_minimum} title={t('sklad.below.title')} sub={t('sklad.below.subTop')} ctx={ctx} more />
          </div>
        </>
      )}
    </SectionData>
  );
}
