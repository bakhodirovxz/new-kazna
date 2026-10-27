import { useState } from 'react';
import type { KaznaSvodOut } from '../../api/types';
import { ItemDialog } from '../obzor/parts/ItemDialog';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { BanksCard } from './parts/BanksCard';
import { CalendarCard } from './parts/CalendarCard';
import { DebtCard } from './parts/DebtCard';
import { KaznaKpis } from './parts/KaznaKpis';
import { OrdersCard } from './parts/OrdersCard';
import { PlanFactCard } from './parts/PlanFactCard';

export default function KaznaSvod({ section, page, filters }: SectionPageProps) {
  const query = useSection<KaznaSvodOut>('/kazna/svod', filters);
  const [item, setItem] = useState<number | null>(null);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <KaznaKpis kpis={data.kpis} />
          <div className="grid">
            <PlanFactCard className="c8 wide" rows={data.plan_fact} limit={5} onItem={setItem} ctx={ctx} />
            <OrdersCard className="c4 wide" orders={data.orders} />
            <CalendarCard className="c7" calendar={data.calendar} ctx={ctx} />
            <BanksCard className="c5" banks={data.banks} date={data.kpis.balance_date} />
            <DebtCard className="c12" contracts={data.contracts} limit={6} hasData={data.kpis.payable !== null || data.kpis.receivable !== null} ctx={ctx} />
          </div>
          {item !== null ? <ItemDialog path={`/kazna/platezhi/items/${item}`} filters={filters} onClose={() => setItem(null)} /> : null}
        </>
      )}
    </SectionData>
  );
}
