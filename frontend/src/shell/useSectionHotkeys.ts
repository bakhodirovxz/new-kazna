import { useEffect } from 'react';

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.getAttribute('role') === 'combobox';
}

/** TZ 6: ← → bo'limlar orasida, agar fokus kiritish maydonida, menyuda, dialogda yoki skroll jadvalda bo'lmasa. */
export function useSectionHotkeys(ids: readonly string[], active: string | null, go: (id: string) => void): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (isTypingTarget(event.target) || document.body.classList.contains('no-scroll')) return;
      if (event.target instanceof HTMLElement && event.target.closest('[role="tablist"],[role="menu"],[role="listbox"],[role="dialog"],[role="alertdialog"],.tw')) return;
      if (ids.length === 0) return;
      const index = active ? ids.indexOf(active) : -1;
      const step = event.key === 'ArrowRight' ? 1 : -1;
      const nextIndex = index < 0 ? (step > 0 ? 0 : ids.length - 1) : (index + step + ids.length) % ids.length;
      const next = ids[nextIndex];
      if (!next) return;
      event.preventDefault();
      go(next);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [ids, active, go]);
}
