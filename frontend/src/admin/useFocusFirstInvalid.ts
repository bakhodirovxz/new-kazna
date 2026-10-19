import { useEffect, useRef } from 'react';

/** Birinchi noto'g'ri maydonga fokus (ekran o'qiydi). errors — barqaror holat obyekti: faqat yangi obyekt qo'yilganda fokus. */
export function useFocusFirstInvalid<T extends HTMLElement = HTMLFormElement>(errors: object) {
  const ref = useRef<T>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  }, [errors]);
  return ref;
}
