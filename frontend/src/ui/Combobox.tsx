import { useEffect, useId, useMemo, useState, type KeyboardEvent } from 'react';
import { t } from '../i18n';
import { cx } from './cx';
import { Field } from './Field';
import './controls.css';

export interface ComboOption {
  value: string;
  label: string;
  hint?: string;
}

export interface ComboboxProps {
  label: string;
  options: readonly ComboOption[];
  value: string | null;
  onChange(value: string | null): void;
  placeholder?: string;
  hint?: string;
  error?: string | null;
  required?: boolean;
  disabled?: boolean;
  emptyText?: string;
}

/** WAI-ARIA 1.2 combobox (list autocomplete): yozish filtrlaydi, ↑↓ Enter tanlaydi, Esc qaytaradi. */
export function Combobox({
  label,
  options,
  value,
  onChange,
  placeholder,
  hint,
  error,
  required,
  disabled,
  emptyText,
}: ComboboxProps) {
  const listId = useId();
  const selectedLabel = options.find((o) => o.value === value)?.label ?? '';
  const [query, setQuery] = useState(selectedLabel);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (!open) setQuery(selectedLabel);
  }, [open, selectedLabel]);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase('ru');
    if (!q || q === selectedLabel.toLocaleLowerCase('ru')) return options;
    return options.filter((o) => o.label.toLocaleLowerCase('ru').includes(q));
  }, [options, query, selectedLabel]);

  const last = filtered.length - 1;
  const current = Math.min(active, last); // -1 faqat ro'yxat bo'sh bo'lsa
  const choose = (option: ComboOption) => {
    onChange(option.value);
    setQuery(option.label);
    setOpen(false);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setActive(0);
      } else setActive(Math.min(current + 1, last));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive(Math.max(current - 1, 0));
    } else if (event.key === 'Enter' && open) {
      const option = filtered[current];
      if (option) {
        event.preventDefault();
        choose(option);
      }
    } else if (event.key === 'Escape' && open) {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
      setQuery(selectedLabel);
    }
  };

  const activeOption = open ? filtered[current] : undefined;

  return (
    <Field label={label} hint={hint} error={error} required={required}>
      {({ id, describedBy, invalid }) => (
        <div className="combo">
          <input
            id={id}
            className="input"
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={activeOption ? `${listId}-${current}` : undefined}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            autoComplete="off"
            placeholder={placeholder ?? t('combo.placeholder')}
            required={required}
            disabled={disabled}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
              setActive(0);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            onKeyDown={onKeyDown}
          />
          <ul id={listId} role="listbox" aria-label={label} className="combo__list" hidden={!open || filtered.length === 0}>
            {filtered.map((option, index) => (
                <li
                  key={option.value}
                  id={`${listId}-${index}`}
                  role="option"
                  tabIndex={-1}
                  aria-selected={option.value === value}
                  className={cx('combo__opt', index === current && 'is-active')}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(option);
                  }}
                >
                  <span>{option.label}</span>
                  {option.hint ? <small>{option.hint}</small> : null}
                </li>
              ))}
          </ul>
          <div role="status" className="combo__empty">
            {open && filtered.length === 0 ? (emptyText ?? t('combo.empty')) : null}
          </div>
        </div>
      )}
    </Field>
  );
}
