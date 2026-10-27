import { useId } from 'react';
import { createPortal } from 'react-dom';
import { t } from '../i18n';
import { Button } from '../ui/Button';
import './screen.css';
import { dismissEnded, useScreenState } from './store';

/** Kiosk paytida sessiya tugasa — jim login sahifasi o'rniga aniq tushuntirish (TZ 6 holatlari). */
export function ScreenEnded() {
  const { ended } = useScreenState();
  const titleId = useId();
  if (!ended) return null;
  return createPortal(
    <div className="screen-ended" role="alertdialog" aria-modal="true" aria-labelledby={titleId}>
      <div className="screen-ended__card">
        <h2 id={titleId}>{t('screen.ended.title')}</h2>
        <p>{t('screen.ended.text')}</p>
        <Button onClick={dismissEnded}>{t('screen.ended.login')}</Button>
      </div>
    </div>,
    document.body,
  );
}
