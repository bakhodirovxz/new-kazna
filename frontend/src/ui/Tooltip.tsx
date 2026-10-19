import { useId, useState, type KeyboardEvent, type ReactNode } from 'react';
import { cx } from './cx';
import './display.css';

export interface TooltipTriggerProps {
  'aria-describedby': string;
  onKeyDown(event: KeyboardEvent<HTMLElement>): void;
  onBlur(): void;
  onMouseLeave(): void;
}

/** Hover/fokusda ko'rinadi (CSS), Esc bilan yopiladi (WCAG 1.4.13). */
export function Tooltip({ content, children }: { content: string; children(trigger: TooltipTriggerProps): ReactNode }) {
  const id = useId();
  const [dismissed, setDismissed] = useState(false);
  const trigger: TooltipTriggerProps = {
    'aria-describedby': id,
    onKeyDown: (event) => {
      if (event.key === 'Escape') setDismissed(true);
    },
    onBlur: () => setDismissed(false),
    onMouseLeave: () => setDismissed(false),
  };
  return (
    <span className={cx('tip', dismissed && 'is-dismissed')}>
      {children(trigger)}
      <span role="tooltip" id={id} className="tip__bubble">
        {content}
      </span>
    </span>
  );
}
