import { useState } from 'react';
import type { KaznaPlatezhiOut } from '../../api/types';
import { ItemDialog } from '../obzor/parts/ItemDialog';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { KaznaKpis } from './parts/KaznaKpis';
import { OrdersCard } from './parts/OrdersCard';
import { PlanFactCard } from './parts/PlanFactCard';

export default function KaznaPlatezhi({ section, page, filters }: SectionPageProps) {
  const query = useSection<KaznaPlatezhiOut>('/kazna/platezhi', filters);
  const [item, setItem] = useState<number | null>(null);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <KaznaKpis kpis={data.kpis} />
          <div className="grid">
            <PlanFactCard className="c8 wide" rows={data.plan_fact} onItem={setItem} ctx={ctx} />
            <OrdersCard className="c4 wide" orders={data.orders} />
          </div>
          {item !== null ? <ItemDialog path={`/kazna/platezhi/items/${item}`} filters={filters} onClose={() => setItem(null)} /> : null}
        </>
      )}
    </SectionData>
  );
}
