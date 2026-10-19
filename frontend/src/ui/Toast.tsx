import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { t } from '../i18n';
import './overlay.css';

export type ToastTone = 'info' | 'success' | 'error';
export const TOAST_MS = 6000;

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

interface ToastApi {
  show(message: string, tone?: ToastTone): void;
}

const ToastContext = createContext<ToastApi | null>(null);

/** Live-hudud `document.body` da: modal ochiqligida `#root` inert bo'lsa ham e'lon qilinadi. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setItems((list) => list.filter((item) => item.id !== id));
  }, []);

  const show = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const id = nextId.current++;
      setItems((list) => [...list.filter((item) => item.message !== message), { id, message, tone }].slice(-4));
      window.setTimeout(() => dismiss(id), TOAST_MS);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {createPortal(
        <div className="toasts" role="status" aria-live="polite" aria-label={t('toast.region')}>
          {items.map((item) => (
            <div key={item.id} className={`toast toast--${item.tone}`}>
              <span>{item.message}</span>
              <button type="button" aria-label={t('overlay.close')} onClick={() => dismiss(item.id)}>
                ×
              </button>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast: ToastProvider topilmadi');
  return context;
}
