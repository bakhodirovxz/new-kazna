import { useState } from 'react';
import type { ObzorSvodOut } from '../../api/types';
import { NoData } from '../../dash/DataState';
import { Rank } from '../../dash/Rank';
import { t } from '../../i18n';
import { buildHash } from '../../router/hash';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { toggleBranch, useSection } from '../useSection';
import { GesMap } from './map/GesMap';
import { StationPanel } from './map/StationPanel';
import { ActivityCard } from './parts/ActivityCard';
import { CashKpis } from './parts/CashKpis';
import { CompareCards } from './parts/CompareCards';
import { FlowCard } from './parts/FlowCard';
import { AllItemsDialog, ItemDialog } from './parts/ItemDialog';

export default function ObzorSvod({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ObzorSvodOut>('/obzor/svod', filters);
  const [item, setItem] = useState<number | null>(null);
  const [all, setAll] = useState<'in' | 'out' | null>(null);
  const [mapSel, setMapSel] = useState<number | null>(null);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => {
        const topBranches = [...data.branches].sort((a, b) => b.outflow - a.outflow).slice(0, 8);
        return (
          <>
            <CashKpis kpis={data.kpis} period={data.period} />
            {data.kpis.has_data ? null : (
              <Card>
                <NoData kind="period" />
              </Card>
            )}
            <div className="grid">
              <CompareCards kpis={data.kpis} months={data.months} period={data.period} ctx={ctx} />
            </div>
            <div className="grid">
              <Card className="c8 wide" title={t('obzor.map.title')} sub={t('obzor.map.sub')}>
                <GesMap stations={data.stations} selected={mapSel ?? filters.br} onSelect={setMapSel} />
              </Card>
              <Card className="c4 wide">
                <StationPanel stations={data.stations} selected={mapSel ?? filters.br} onSelect={setMapSel} filters={filters} onBranch={onBranch} />
              </Card>
            </div>
            <div className="grid">
              <FlowCard months={data.months} ctx={ctx} className="c8" />
              <ActivityCard activity={data.activity} className="c4" />
              <Card className="c4" title={t('obzor.branchesOut.title')} sub={filters.br === null ? t('obzor.branchesOut.subAll') : t('obzor.branchesOut.subOne')}>
                <Rank
                  label={t('obzor.branchesOut.title')}
                  items={topBranches.map((b) => ({ id: b.branch_id, name: b.name, value: b.outflow }))}
                  onSelect={(id) => toggleBranch(filters, Number(id), onBranch)}
                  activeId={filters.br}
                />
                {filters.br === null ? (
                  <a className="more" href={buildHash({ kind: 'section', section: 'obzor', page: 'rasxod', br: null, per: filters.per })}>
                    {t('obzor.allBranches')}
                  </a>
                ) : null}
              </Card>
              <Card className="c4" title={t('obzor.topIn.title')} sub={t('obzor.top.sub')}>
                <Rank label={t('obzor.topIn.title')} items={data.items_in.slice(0, 5).map((i) => ({ id: i.item_id, name: i.name, value: i.amount }))} onSelect={(id) => setItem(Number(id))} />
                <button type="button" className="more" onClick={() => setAll('in')}>
                  {t('obzor.allItems')}
                </button>
              </Card>
              <Card className="c4" title={t('obzor.topOut.title')} sub={t('obzor.top.sub')}>
                <Rank label={t('obzor.topOut.title')} items={data.items_out.slice(0, 5).map((i) => ({ id: i.item_id, name: i.name, value: i.amount }))} onSelect={(id) => setItem(Number(id))} />
                <button type="button" className="more" onClick={() => setAll('out')}>
                  {t('obzor.allItems')}
                </button>
              </Card>
            </div>
            {all ? (
              <AllItemsDialog
                title={all === 'in' ? t('obzor.allItemsIn') : t('obzor.allItemsOut')}
                items={all === 'in' ? data.items_in : data.items_out}
                onPick={(id) => {
                  setAll(null);
                  setItem(id);
                }}
                onClose={() => setAll(null)}
              />
            ) : null}
            {item !== null ? <ItemDialog path={`/obzor/items/${item}`} filters={filters} onClose={() => setItem(null)} /> : null}
          </>
        );
      }}
    </SectionData>
  );
}
