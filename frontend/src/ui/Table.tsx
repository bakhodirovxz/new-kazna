/* Явные роли: в карточном режиме (display:block) Safari/VoiceOver теряют семантику таблицы. */
/* eslint-disable jsx-a11y/no-redundant-roles, jsx-a11y/no-interactive-element-to-noninteractive-role */
import { useMemo, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react';
import { t } from '../i18n';
import { cx } from './cx';
import { Select } from './Select';
import './table.css';

export interface Column<T> {
  key: string;
  header: string;
  cell(row: T): ReactNode;
  sortValue?(row: T): string | number | null;
  align?: 'left' | 'right';
  wrap?: boolean;
}

export interface SortState {
  key: string;
  dir: 'asc' | 'desc';
}

export interface TableProps<T> {
  caption: string;
  captionHidden?: boolean;
  columns: readonly Column<T>[];
  rows: readonly T[];
  rowKey(row: T): string | number;
  onRowClick?(row: T): void;
  activeKey?: string | number | null;
  empty?: ReactNode;
  initialSort?: SortState;
  mobile?: 'cards' | 'scroll';
  /** true — balandlik cheklanmaydi (sahifa bo'yi jadval). */
  free?: boolean;
  footer?: ReactNode;
  className?: string;
  /** Таблица внутри карточки: без собственной рамки. */
  bare?: boolean;
}

const collator = new Intl.Collator('ru', { numeric: true });
const INTERACTIVE = 'button, a, input, select, textarea, label, [role="button"], [role="link"]';

/** Cheksiz/NaN son qiymatlar null kabi — oxirida. */
function norm(v: string | number | null): string | number | null {
  return typeof v === 'number' && !Number.isFinite(v) ? null : v;
}

function compare(a: string | number | null, b: string | number | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return collator.compare(String(a), String(b));
}

export function Table<T>({
  caption,
  captionHidden = true,
  columns,
  rows,
  rowKey,
  onRowClick,
  activeKey = null,
  empty,
  initialSort,
  mobile = 'cards',
  free = false,
  footer,
  className,
  bare = false,
}: TableProps<T>) {
  const [sort, setSort] = useState<SortState | null>(initialSort ?? null);

  const sorted = useMemo(() => {
    const column = sort ? columns.find((c) => c.key === sort.key) : undefined;
    if (!sort || !column?.sortValue) return rows;
    const value = column.sortValue;
    const sign = sort.dir === 'asc' ? 1 : -1;
    return [...rows].sort((x, y) => {
      const a = norm(value(x));
      const b = norm(value(y));
      if (a === null || b === null) return compare(a, b);
      return sign * compare(a, b);
    });
  }, [rows, columns, sort]);

  const toggle = (key: string) => {
    setSort((current) =>
      current?.key === key ? { key, dir: current.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' },
    );
  };

  const onRowClickEvent = (event: MouseEvent<HTMLTableRowElement>, row: T) => {
    const match = (event.target as HTMLElement).closest(INTERACTIVE);
    if (match && match !== event.currentTarget && event.currentTarget.contains(match)) return;
    onRowClick?.(row);
  };

  const onRowKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, row: T) => {
    // Ichki tugma/havoladan ko'tarilgan klavish qatorni faollashtirmasin.
    if (event.target !== event.currentTarget) return;
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onRowClick?.(row);
  };

  const sortColumn = sort ? columns.find((c) => c.key === sort.key) : undefined;

  const sortable = columns.filter((c) => c.sortValue);
  const sortOptions = [
    { value: '', label: t('table.sortNone') },
    ...sortable.flatMap((c) => [
      { value: `${c.key}:asc`, label: `${c.header} ↑` },
      { value: `${c.key}:desc`, label: `${c.header} ↓` },
    ]),
  ];
  const onSortSelect = (v: string) => {
    const i = v.lastIndexOf(':');
    setSort(i < 0 ? null : { key: v.slice(0, i), dir: v.slice(i + 1) === 'desc' ? 'desc' : 'asc' });
  };

  return (
    <div className={cx('tw', mobile === 'cards' && 'tw--cards', free && 'tw--free', bare && 'tw--bare', className)}>
      {mobile === 'cards' && sortable.length > 0 ? (
        <Select
          className="tw__sort"
          label={t('table.sortBy')}
          value={sort ? `${sort.key}:${sort.dir}` : ''}
          options={sortOptions}
          onChange={onSortSelect}
        />
      ) : null}
      <table className="table" role="table">
        <caption className={captionHidden ? 'visually-hidden' : undefined}>{caption}</caption>
        <thead role="rowgroup">
          <tr role="row">
            {columns.map((column) => {
              const dir = sort !== null && sort.key === column.key ? sort.dir : null;
              return (
                <th
                  key={column.key}
                  scope="col"
                  role="columnheader"
                  className={cx(column.align === 'left' && 'l')}
                  aria-sort={dir ? (dir === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  {column.sortValue ? (
                    <button
                      type="button"
                      className="th-sort"
                      data-dir={dir ?? undefined}
                      onClick={() => toggle(column.key)}
                    >
                      {column.header}
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody role="rowgroup">
          {sorted.length === 0 ? (
            <tr role="row">
              <td role="cell" colSpan={columns.length} className="empty">
                {empty ?? t('table.empty')}
              </td>
            </tr>
          ) : (
            sorted.map((row) => {
              const key = rowKey(row);
              const clickable = Boolean(onRowClick);
              return (
                <tr
                  role="row"
                  key={key}
                  className={cx(clickable && 'click', activeKey === key && 'active')}
                  tabIndex={clickable ? 0 : undefined}
                  onClick={clickable ? (event) => onRowClickEvent(event, row) : undefined}
                  onKeyDown={clickable ? (event) => onRowKeyDown(event, row) : undefined}
                >
                  {columns.map((column) => (
                    <td
                      role="cell"
                      key={column.key}
                      data-label={column.header}
                      className={cx(column.align === 'left' && 'l', column.wrap && 'w')}
                    >
                      {column.cell(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
        {footer ? <tfoot role="rowgroup">{footer}</tfoot> : null}
      </table>
      <span className="visually-hidden" role="status">
        {sort && sortColumn?.sortValue
          ? t(sort.dir === 'asc' ? 'table.sortAsc' : 'table.sortDesc', { column: sortColumn.header })
          : ''}
      </span>
    </div>
  );
}
