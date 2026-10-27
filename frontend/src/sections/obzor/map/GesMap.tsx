import { useId, type KeyboardEvent } from 'react';
import type { StationOut } from './types';
import { formatMoney } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { cx } from '../../../ui/cx';
import { HIDDEN_LABELS, inInset, insetXY, LABEL_SIDE, mainXY, markerRadius, UZ_GEO } from './geo';
import './map.css';

export interface GesMapProps {
  stations: readonly StationOut[];
  selected: number | null;
  onSelect(id: number | null): void;
}

function tip(s: StationOut): string {
  if (s.kind === 'head') return t('obzor.map.tipHq', { name: s.name, balance: formatMoney(s.closing) });
  return t('obzor.map.tip', { name: s.name, capacity: formatNumber(s.capacity_mw ?? 0), outflow: formatMoney(s.outflow) });
}

function lowPlan(s: StationOut): boolean {
  const execution = s.production?.execution;
  return execution !== undefined && execution < 0.95;
}

function Marker({ s, x, y, r, on, onSelect }: { s: StationOut; x: number; y: number; r: number; on: boolean; onSelect(id: number | null): void }) {
  const hq = s.kind === 'head';
  const side = LABEL_SIDE[s.code] ?? 'r';
  const off = r + 5;
  const lx = side === 'l' ? x - off : side === 'r' ? x + off : x;
  const ly = side === 't' ? y - off - 2 : side === 'b' ? y + off + 11 : y + 4.5;
  const anchor = side === 'l' ? 'end' : side === 'r' ? 'start' : 'middle';
  const text = tip(s);
  const toggle = () => onSelect(on ? null : s.branch_id);
  const onKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      toggle();
    }
  };
  return (
    <g className={cx('ges', on && 'is-on')} role="button" tabIndex={0} aria-pressed={on} aria-label={text} onClick={toggle} onKeyDown={onKeyDown}>
      <title>{text}</title>
      {on ? <circle className="ges__sel" cx={x} cy={y} r={r + 6} /> : null}
      <circle className="ges__ring" cx={x} cy={y} r={r + 3} />
      {hq ? (
        <rect className="ges__dot ges__dot--hq" x={x - r} y={y - r} width={2 * r} height={2 * r} rx={3} />
      ) : (
        <circle className={cx('ges__dot', lowPlan(s) && 'is-low')} cx={x} cy={y} r={r} />
      )}
      <text x={lx} y={ly} textAnchor={anchor}>
        {s.short_name}
      </text>
    </g>
  );
}

/** TZ 6 «Карта ГЭС»: stansiyalar koordinatalar bo'yicha, Toshkent viloyati — alohida ramkada. */
export function GesMap({ stations, selected, onSelect }: GesMapProps) {
  const clipId = `ins${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const [ix, iy, iw, ih] = UZ_GEO.inset;
  const [bx0, by0] = mainXY(68.95, 41.75);
  const [bx1, by1] = mainXY(70.15, 40.95);
  const placed = stations.filter((s) => s.lat !== null && s.lon !== null);
  const anyLow = placed.some(lowPlan);
  return (
    <div className="mapwrap">
      <svg viewBox={`0 0 ${UZ_GEO.W} ${UZ_GEO.H}`} role="group" aria-label={t('obzor.map.aria')}>
        <defs>
          <clipPath id={clipId}>
            <rect x={ix} y={iy} width={iw} height={ih} rx={8} />
          </clipPath>
        </defs>
        {UZ_GEO.reg.map((r) => (
          <path key={r.n} className={cx('reg', r.city && 'reg--city')} d={r.d} />
        ))}
        {UZ_GEO.reg
          .filter((r) => r.x !== undefined && !HIDDEN_LABELS.includes(r.n))
          .map((r) => (
            <text key={`l-${r.n}`} className="regl" x={r.x} y={r.y}>
              {r.n}
            </text>
          ))}
        <rect className="map__box" x={bx0} y={by0} width={bx1 - bx0} height={by1 - by0} />
        <path className="map__box" d={`M${bx1},${by0} L${ix},${iy + ih}`} />
        {placed
          .filter((s) => inInset(s.lon ?? 0, s.lat ?? 0))
          .map((s) => {
            const [x, y] = mainXY(s.lon ?? 0, s.lat ?? 0);
            return <circle key={`c-${s.branch_id}`} className="map__cluster" cx={x} cy={y} r={2.6} />;
          })}
        <rect className="map__inset" x={ix} y={iy} width={iw} height={ih} rx={8} />
        <g clipPath={`url(#${clipId})`}>
          {UZ_GEO.ins.map((d, i) => (
            <path key={`i-${i}`} className={cx('reg', UZ_GEO.reg[i]?.city && 'reg--city')} d={d} />
          ))}
        </g>
        <text className="regl regl--start" x={ix + 8} y={iy + ih - 8}>
          {t('obzor.map.inset')}
        </text>
        {placed.map((s) => {
          const lon = s.lon ?? 0;
          const lat = s.lat ?? 0;
          const inset = inInset(lon, lat);
          const [x, y] = inset ? insetXY(lon, lat) : mainXY(lon, lat);
          return (
            <Marker key={s.branch_id} s={s} x={x} y={y} r={markerRadius(s.capacity_mw, inset, s.kind === 'head')} on={selected === s.branch_id} onSelect={onSelect} />
          );
        })}
      </svg>
      <div className="maplegend">
        <span>
          <i className="maplegend__ok" />
          {t('obzor.map.legendOk')}
        </span>
        {anyLow ? (
          <span>
            <i className="maplegend__low" />
            {t('obzor.map.legendLow')}
          </span>
        ) : null}
        <span>
          <i className="maplegend__hq" />
          {t('obzor.map.legendHq')}
        </span>
      </div>
    </div>
  );
}
