import { useEffect, useLayoutEffect, useRef, type MouseEvent, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { cx } from './cx';
import './overlay.css';

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

let openCount = 0;
// Ochiq qatlamlar steki: hujjat darajasidagi Tab/Esc faqat eng ustkisiga tegishli.
const stack: symbol[] = [];

/** Trigger DOM'dan o'chgan bo'lsa: sahifaning barqaror nuqtasi (h1 / main / #root). */
function focusFallback(): void {
  const target =
    document.querySelector<HTMLElement>('main h1') ??
    document.querySelector<HTMLElement>('main') ??
    document.getElementById('root')?.querySelector<HTMLElement>(FOCUSABLE) ??
    null;
  if (!target) return;
  if (!target.matches(FOCUSABLE)) target.tabIndex = -1;
  target.focus();
}

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
  role?: 'dialog' | 'alertdialog';
  describedBy?: string;
  /** false bo'lsa Esc va fon yopmaydi (masalan, so'rov ketayotganda). */
  dismissible?: boolean;
  className?: string;
  children: ReactNode;
}

/** Barcha modal qatlamlar asosi: portal, aria-modal, fokus tuzog'i, Esc, fon, inert ilova, fokusni qaytarish. */
export function Overlay({
  open,
  onClose,
  variant,
  labelledBy,
  label,
  initialFocusRef,
  role = 'dialog',
  describedBy,
  dismissible = true,
  className,
  children,
}: OverlayProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const downOnBackdrop = useRef(false);
  const latest = useRef({ onClose, dismissible });
  latest.current = { onClose, dismissible };

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    openCount += 1;
    const token = Symbol('overlay');
    stack.push(token);
    if (openCount === 1) {
      setAppInert(true);
      document.body.classList.add('no-scroll');
    }
    const panel = panelRef.current;
    const target = initialFocusRef?.current ?? panel?.querySelector<HTMLElement>(FOCUSABLE) ?? panel;
    target?.focus();

    // Hujjat darajasida: fokus panel ichida bo'lmasa ham (disabled tugma, body) Tab/Esc ishlaydi.
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (stack[stack.length - 1] !== token || !panel) return;
      if (event.key === 'Escape') {
        event.stopPropagation();
        if (latest.current.dismissible) latest.current.onClose();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (!first || !last) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const inside = active instanceof Node && panel.contains(active) && active !== panel;
      if (event.shiftKey && (!inside || active === first)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (!inside || active === last)) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      stack.splice(stack.indexOf(token), 1);
      openCount -= 1;
      if (openCount === 0) {
        setAppInert(false);
        document.body.classList.remove('no-scroll');
      }
      if (previous?.isConnected) previous.focus();
      else focusFallback();
    };
  }, [open, initialFocusRef]);

  // Fokus body'ga tushsa (fokuslangan tugma disabled bo'ldi): panelga qaytaramiz.
  useLayoutEffect(() => {
    if (open && document.activeElement === document.body) panelRef.current?.focus();
  });

  if (!open) return null;

  const onBackdropDown = (event: MouseEvent<HTMLDivElement>) => {
    downOnBackdrop.current = event.target === event.currentTarget;
  };

  // Scrollbar'da mousedown yoki matn tanlab fonda qo'yib yuborish yopmasin: ikkala hodisa ham fonda bo'lishi shart.
  const onBackdropClick = (event: MouseEvent<HTMLDivElement>) => {
    if (downOnBackdrop.current && event.target === event.currentTarget && dismissible) onClose();
    downOnBackdrop.current = false;
  };

  return createPortal(
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions, jsx-a11y/click-events-have-key-events -- fon: sichqoncha bilan yopish; klaviaturada Esc
    <div className={cx('overlay', `overlay--${variant}`)} onMouseDown={onBackdropDown} onClick={onBackdropClick}>
      <div
        ref={panelRef}
        className={cx('overlay__panel', className)}
        role={role}
        aria-describedby={describedBy}
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={labelledBy ? undefined : label}
        tabIndex={-1}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
