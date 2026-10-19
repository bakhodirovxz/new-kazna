import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import type { MeOut, MenuOut } from '../api/types';
import { t } from '../i18n';
import { useBranches, usePeriods } from '../meta/api';
import type { Route } from '../router/hash';
import { navigate } from '../router/store';
import { cx } from '../ui/cx';
import { Overlay } from '../ui/Overlay';
import { buildPaletteItems, filterPalette, type PaletteItem } from './paletteItems';

export interface CommandPaletteProps {
  open: boolean;
  onClose(): void;
  me: MeOut;
  menu: MenuOut;
  route: Route;
}

export function CommandPalette({ open, onClose, me, menu, route }: CommandPaletteProps) {
  const branches = useBranches();
  const periods = usePeriods();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  useEffect(() => {
    if (open) {
      setQuery('');
      setActive(0);
    }
  }, [open]);

  const items = useMemo(
    () =>
      buildPaletteItems({
        menu,
        permissions: me.permissions,
        branches: branches.data ?? [],
        periods: periods.data?.items ?? [],
        defaultPeriod: periods.data?.default ?? 'ytd',
        locked: me.branch_ids !== null && me.branch_ids.length === 1,
        route,
      }),
    [menu, me, branches.data, periods.data, route],
  );
  const results = useMemo(() => filterPalette(items, query), [items, query]);

  const choose = (item: PaletteItem) => {
    onClose();
    navigate(item.target);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === 'Enter') {
      const item = results[active];
      if (item) {
        event.preventDefault();
        choose(item);
      }
    }
  };

  return (
    <Overlay open={open} onClose={onClose} variant="palette" label={t('palette.label')} initialFocusRef={inputRef}>
      <input
        ref={inputRef}
        className="palette__input"
        role="combobox"
        aria-expanded="true"
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={results[active] ? `${listId}-${active}` : undefined}
        aria-label={t('palette.label')}
        placeholder={t('palette.placeholder')}
        autoComplete="off"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
        }}
        onKeyDown={onKeyDown}
      />
      <ul id={listId} role="listbox" aria-label={t('palette.results')} className="palette__list">
        {results.length === 0 ? (
          <li className="palette__empty" role="presentation">
            {t('palette.empty')}
          </li>
        ) : (
          results.map((item, index) => (
            <li
              key={item.id}
              id={`${listId}-${index}`}
              role="option"
              tabIndex={-1}
              aria-selected={index === active}
              className={cx('palette__opt', index === active && 'is-active')}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(item);
              }}
              onMouseEnter={() => setActive(index)}
            >
              <span>{item.label}</span>
              <span className="palette__kind">{item.kindLabel}</span>
            </li>
          ))
        )}
      </ul>
      <div className="palette__hint" aria-hidden="true">
        <span>
          <kbd>↑</kbd> <kbd>↓</kbd> {t('palette.hintMove')}
        </span>
        <span>
          <kbd>Enter</kbd> {t('palette.hintOpen')}
        </span>
        <span>
          <kbd>Esc</kbd> {t('palette.hintClose')}
        </span>
      </div>
    </Overlay>
  );
}
