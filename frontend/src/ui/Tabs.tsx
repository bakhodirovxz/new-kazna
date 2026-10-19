import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';
import './display.css';

export interface TabItem {
  id: string;
  label: string;
}

export interface TabsProps {
  label: string;
  tabs: readonly TabItem[];
  value: string;
  onChange(id: string): void;
  children: ReactNode;
}

/** WAI-ARIA tabs: roving tabindex, ←/→/Home/End, avtomatik faollashtirish. */
export function Tabs({ label, tabs, value, onChange, children }: TabsProps) {
  const base = useId();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const index = Math.max(
    0,
    tabs.findIndex((tab) => tab.id === value),
  );

  const move = (next: number) => {
    const target = tabs[(next + tabs.length) % tabs.length];
    if (!target) return;
    onChange(target.id);
    refs.current[(next + tabs.length) % tabs.length]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowRight') move(index + 1);
    else if (event.key === 'ArrowLeft') move(index - 1);
    else if (event.key === 'Home') move(0);
    else if (event.key === 'End') move(tabs.length - 1);
    else return;
    event.preventDefault();
  };

  return (
    <div className="tabs">
      <div role="tablist" aria-label={label} className="tabs__list">
        {tabs.map((tab, i) => (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`${base}-tab-${tab.id}`}
            aria-selected={tab.id === value}
            aria-controls={`${base}-panel`}
            tabIndex={i === index ? 0 : -1}
            className="tabs__tab"
            onClick={() => onChange(tab.id)}
            onKeyDown={onKeyDown}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`${base}-panel`}
        aria-labelledby={`${base}-tab-${tabs[index]?.id ?? ''}`}
        className="tabs__panel"
        tabIndex={0}
      >
        {children}
      </div>
    </div>
  );
}
