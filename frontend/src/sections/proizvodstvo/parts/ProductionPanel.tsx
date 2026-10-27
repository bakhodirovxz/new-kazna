import type { MapStationOut } from '../../../api/types';
import { formatKwh } from '../../../dash/energy';
import { ProductionBlock } from '../../../dash/map/ProductionBlock';
import '../../../dash/map/map.css';
import { formatPct } from '../../../dash/money';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Button } from '../../../ui/Button';

export interface ProductionPanelProps {
  stations: readonly MapStationOut[];
  selected: number | null;
  onSelect(id: number | null): void;
  filters: FilterState;
  onBranch(br: number | null): void;
}

/** Prototip `gesPanel` (ishlab chiqarish qismi): tanlanmagan — stansiyalar ro'yxati, tanlangan — ko'rsatkichlar. */
export function ProductionPanel({ stations, selected, onSelect, filters, onBranch }: ProductionPanelProps) {
  const station = stations.find((s) => s.branch_id === selected);
  if (!station) {
    const list = stations
      .filter((s) => s.kind !== 'head' && s.production !== null)
      .sort((a, b) => (b.production?.generation ?? 0) - (a.production?.generation ?? 0));
    return (
      <div className="gp">
        <div className="gp-h">
          <div>
            <h2>{t('proizv.panel.all')}</h2>
            <p className="note">{t('proizv.panel.allNote', { count: list.length })}</p>
          </div>
        </div>
        <Rank
          label={t('proizv.panel.all')}
          items={list.map((s) => ({
            id: s.branch_id,
            name: s.name,
            value: s.production?.generation ?? 0,
            note: t('proizv.rank.ofPlan', { pct: formatPct(s.production?.execution ?? null, 0) }),
            negative: (s.production?.execution ?? 1) < 0.95,
          }))}
          format={(v) => formatKwh(v)}
          onSelect={(id) => onSelect(Number(id))}
        />
      </div>
    );
  }
  const hq = station.kind === 'head';
  return (
    <div className="gp">
      <div className="gp-h">
        <h2>{station.name}</h2>
        <button type="button" className="gp-x" onClick={() => onSelect(null)}>
          {t('proizv.panel.all')}
        </button>
      </div>
      {hq ? <p className="note">{t('proizv.panel.hq')}</p> : <ProductionBlock capacity={station.capacity_mw} production={station.production} />}
      {hq || filters.br === station.branch_id ? null : (
        <Button variant="secondary" onClick={() => onBranch(station.branch_id)}>
          {t('proizv.panel.open')}
        </Button>
      )}
    </div>
  );
}
