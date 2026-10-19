import { useEffect, useId, useState, type ReactNode } from 'react';
import { cx } from './cx';
import './display.css';

export interface TooltipTriggerProps {
  'aria-describedby': string;
}

/** Hover/fokusda ko'rinadi (CSS), Esc bilan yopiladi — hover'da ham (WCAG 1.4.13). */
export function Tooltip({ content, children }: { content: string; children(trigger: TooltipTriggerProps): ReactNode }) {
  const id = useId();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const visible = hovered || focused;

  // Esc faqat izoh ko'rinib turganda tinglanadi (fokus trigger'da bo'lmasa ham ishlashi uchun document'da).
  useEffect(() => {
    if (!visible || dismissed) return;
    // capture + stopPropagation: Esc dialog ichida avval faqat izohni yopadi (eng ichki qatlam), dialogni emas.
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      setDismissed(true);
    };
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [visible, dismissed]);

  useEffect(() => {
    if (!visible) setDismissed(false);
  }, [visible]);

  return (
    <span
      className={cx('tip', dismissed && 'is-dismissed')}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
    >
      {children({ 'aria-describedby': id })}
      <span role="tooltip" id={id} className="tip__bubble">
        {content}
      </span>
    </span>
  );
}
