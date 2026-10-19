import { useEffect, useRef, type KeyboardEvent, type MouseEvent, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { cx } from './cx';
import './overlay.css';

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

let openCount = 0;

function setAppInert(inert: boolean): void {
  const root = document.getElementById('root');
  if (!root) return;
  if (inert) root.setAttribute('inert', '');
  else root.removeAttribute('inert');
}

export type OverlayVariant = 'modal' | 'drawer' | 'sheet' | 'palette';

export interface OverlayProps {
  open: boolean;
  onClose(): void;
  variant: OverlayVariant;
  labelledBy?: string;
  label?: string;
  initialFocusRef?: RefObject<HTMLElement>;
  className?: string;
  children: ReactNode;
}

/** Barcha modal qatlamlar asosi: portal, aria-modal, fokus tuzog'i, Esc, fon, inert ilova, fokusni qaytarish. */
export function Overlay({ open, onClose, variant, labelledBy, label, initialFocusRef, className, children }: OverlayProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    openCount += 1;
    if (openCount === 1) {
      setAppInert(true);
      document.body.classList.add('no-scroll');
    }
    const panel = panelRef.current;
    const target = initialFocusRef?.current ?? panel?.querySelector<HTMLElement>(FOCUSABLE) ?? panel;
    target?.focus();
    return () => {
      openCount -= 1;
      if (openCount === 0) {
        setAppInert(false);
        document.body.classList.remove('no-scroll');
      }
      previous?.focus();
    };
  }, [open, initialFocusRef]);

  if (!open) return null;

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== 'Tab') return;
    const items = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    const first = items[0];
    const last = items[items.length - 1];
    if (!first || !last) {
      event.preventDefault();
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const onBackdrop = (event: MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) onClose();
  };

  return createPortal(
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions -- fon: sichqoncha bilan yopish; klaviaturada Esc
    <div className={cx('overlay', `overlay--${variant}`)} onMouseDown={onBackdrop}>
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- dialog: Tab tuzog'i va Esc */}
      <div
        ref={panelRef}
        className={cx('overlay__panel', className)}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={labelledBy ? undefined : label}
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
