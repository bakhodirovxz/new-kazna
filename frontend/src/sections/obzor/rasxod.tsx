import { useState } from 'react';
import type { ObzorFlowOut } from '../../api/types';
import { NoData } from '../../dash/DataState';
import { Rank } from '../../dash/Rank';
import { t } from '../../i18n';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { ActivityCard } from './parts/ActivityCard';
import { BranchAmountTable } from './parts/BranchAmountTable';
import { CashKpis } from './parts/CashKpis';
import { ItemDialog } from './parts/ItemDialog';
import { SeriesChart } from './parts/SeriesChart';

export default function ObzorRasxod({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ObzorFlowOut>('/obzor/rasxod', filters);
  const [item, setItem] = useState<number | null>(null);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <CashKpis kpis={data.kpis} period={data.period} />
          <div className="grid">
            <SeriesChart data={data} title={t('obzor.rasxod.monthly')} sub={t('obzor.rasxod.monthlySub')} ctx={ctx} className="c8" />
            <ActivityCard activity={data.activity} className="c4" />
            <Card className="c6" title={t('obzor.rasxod.items')} sub={t('obzor.top.sub')}>
              {data.items.length ? (
                <Rank label={t('obzor.rasxod.items')} items={data.items.map((i) => ({ id: i.item_id, name: i.name, value: i.amount }))} onSelect={(id) => setItem(Number(id))} />
              ) : (
                <NoData kind="period" />
              )}
            </Card>
            <Card className="c6" title={t('obzor.rasxod.banks')} sub={t('obzor.rasxod.banksSub')}>
              <Rank label={t('obzor.rasxod.banks')} items={data.banks.map((b) => ({ id: b.bank_name, name: b.bank_name, value: b.amount }))} />
            </Card>
            <BranchAmountTable className="c12" title={t('obzor.rasxod.branches')} label={t('obzor.kpi.outflow')} rows={data.branches} filters={filters} onBranch={onBranch} ctx={ctx} />
          </div>
          {item !== null ? <ItemDialog path={`/obzor/items/${item}`} filters={filters} onClose={() => setItem(null)} /> : null}
        </>
      )}
    </SectionData>
  );
}
