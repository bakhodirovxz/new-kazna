import type { StationOut } from '../../../api/types';
import { formatMoney } from '../../../dash/money';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Button } from '../../../ui/Button';
import './map.css';

export interface StationPanelProps {
  stations: readonly StationOut[];
  selected: number | null;
  onSelect(id: number | null): void;
  filters: FilterState;
  onBranch(br: number | null): void;
}

function Row({ label, value, negative }: { label: string; value: number | null; negative?: boolean }) {
  return (
    <li>
      <span>{label}</span>
      <b className={negative ? 'neg' : undefined}>{formatMoney(value)}</b>
    </li>
  );
}

export function StationPanel({ stations, selected, onSelect, filters, onBranch }: StationPanelProps) {
  const station = stations.find((s) => s.branch_id === selected);
  if (!station) {
    const list = stations.filter((s) => s.kind !== 'head').sort((a, b) => b.outflow - a.outflow);
    return (
      <div className="gp">
        <div className="gp-h">
          <div>
            <h2>{t('obzor.station.all')}</h2>
            <p className="note">{t('obzor.station.allNote', { count: list.length })}</p>
          </div>
        </div>
        <Rank label={t('obzor.station.byOutflow')} items={list.map((s) => ({ id: s.branch_id, name: s.name, value: s.outflow }))} onSelect={(id) => onSelect(Number(id))} />
      </div>
    );
  }
  const hq = station.kind === 'head';
  const overdueShare = station.payable ? (station.overdue_payable ?? 0) / station.payable : 0;
  return (
    <div className="gp">
      <div className="gp-h">
        <h2>{station.name}</h2>
        <button type="button" className="gp-x" onClick={() => onSelect(null)}>
          {t('obzor.station.all')}
        </button>
      </div>
      {hq ? (
        <p className="note">{t('obzor.station.hqNote')}</p>
      ) : (
        <>
          <div className="gp-grid">
            <div>
              <span>{t('obzor.station.capacity')}</span>
              <b>
                {station.capacity_mw == null ? (
                  '—'
                ) : (
                  <>
                    {formatNumber(station.capacity_mw)}
                    <small>{t('obzor.station.mw')}</small>
                  </>
                )}
              </b>
            </div>
          </div>
          <p className="note">{t('obzor.station.noProduction')}</p>
        </>
      )}
      <ul className="gp-rows">
        <Row label={t('obzor.station.inflow')} value={station.inflow} />
        <Row label={t('obzor.station.outflow')} value={station.outflow} />
        <Row label={t('obzor.station.closing')} value={station.closing} />
        <Row label={t('obzor.station.receivable')} value={station.receivable} />
        <Row label={t('obzor.station.payable')} value={station.payable} />
        <Row label={t('obzor.station.overdue')} value={station.overdue_payable} negative={overdueShare > 0.2} />
      </ul>
      {filters.br === station.branch_id ? null : (
        <Button variant="secondary" onClick={() => onBranch(station.branch_id)}>
          {hq ? t('obzor.station.openHq') : t('obzor.station.openStation')}
        </Button>
      )}
    </div>
  );
}
