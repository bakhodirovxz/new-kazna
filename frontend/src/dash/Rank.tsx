import { formatPct, formatMoney } from './money';
import './dash.css';

export interface RankItem {
  id: string | number;
  name: string;
  value: number;
  note?: string;
  mark?: number;
  negative?: boolean;
}

export interface RankProps {
  label: string;
  items: readonly RankItem[];
  format?: (value: number) => string;
  onSelect?: (id: string | number) => void;
  activeId?: string | number | null;
}

/** Prototip `rank()`: nom, summa, ulush va gorizontal chiziq; bosilsa — tanlash. */
export function Rank({ label, items, format = (v) => formatMoney(v), onSelect, activeId }: RankProps) {
  const total = items.reduce((s, x) => s + x.value, 0);
  const max = Math.max(1e-9, ...items.map((x) => x.value));
  return (
    <ul className="rank" aria-label={label}>
      {items.map((x) => {
        const inner = (
          <>
            <span className="rank__n">{x.name}</span>
            <span className="rank__a">
              {format(x.value)}
              <small>{x.note ?? formatPct(total ? x.value / total : null)}</small>
            </span>
            <span className="rank__b" aria-hidden="true">
              <i className={x.negative ? 'is-neg' : undefined} style={{ width: `${(x.value / max) * 100}%` }} />
              {x.mark !== undefined ? <u style={{ left: `${Math.min(100, (x.mark / max) * 100)}%` }} /> : null}
            </span>
          </>
        );
        return (
          <li key={x.id}>
            {onSelect ? (
              <button type="button" aria-pressed={activeId === x.id} onClick={() => onSelect(x.id)}>
                {inner}
              </button>
            ) : (
              <div className="rank__row">{inner}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
