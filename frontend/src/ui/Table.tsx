import { useMemo, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react';
import { t } from '../i18n';
import { cx } from './cx';
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
}

function compare(a: string | number | null, b: string | number | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), 'ru');
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
}: TableProps<T>) {
  const [sort, setSort] = useState<SortState | null>(initialSort ?? null);

  const sorted = useMemo(() => {
    const column = sort ? columns.find((c) => c.key === sort.key) : undefined;
    if (!sort || !column?.sortValue) return rows;
    const value = column.sortValue;
    const sign = sort.dir === 'asc' ? 1 : -1;
    return [...rows].sort((x, y) => {
      const a = value(x);
      const b = value(y);
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
    if ((event.target as HTMLElement).closest('button, a, input, select, textarea, label')) return;
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

  return (
    <div className={cx('tw', mobile === 'cards' && 'tw--cards', free && 'tw--free', className)}>
      <table className="table">
        <caption className={captionHidden ? 'visually-hidden' : undefined}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => {
              const dir = sort !== null && sort.key === column.key ? sort.dir : null;
              return (
                <th
                  key={column.key}
                  scope="col"
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
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="empty">
                {empty ?? t('table.empty')}
              </td>
            </tr>
          ) : (
            sorted.map((row) => {
              const key = rowKey(row);
              const clickable = Boolean(onRowClick);
              return (
                <tr
                  key={key}
                  className={cx(clickable && 'click', activeKey === key && 'active')}
                  tabIndex={clickable ? 0 : undefined}
                  onClick={clickable ? (event) => onRowClickEvent(event, row) : undefined}
                  onKeyDown={clickable ? (event) => onRowKeyDown(event, row) : undefined}
                >
                  {columns.map((column) => (
                    <td
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
        {footer ? <tfoot>{footer}</tfoot> : null}
      </table>
      <span className="visually-hidden" role="status">
        {sort && sortColumn?.sortValue
          ? t(sort.dir === 'asc' ? 'table.sortAsc' : 'table.sortDesc', { column: sortColumn.header })
          : ''}
      </span>
    </div>
  );
}
