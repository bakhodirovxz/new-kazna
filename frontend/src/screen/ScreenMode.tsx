import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { MenuOut } from '../api/types';
import { t } from '../i18n';
import type { Route } from '../router/hash';
import { useMediaQuery } from '../shell/useMediaQuery';
import { Icon } from '../ui/icons';
import './screen.css';
import { startScreen, stopScreen, useScreenState } from './store';
import { useScreenRotation } from './useScreenRotation';

/** TZ 6 «Режим экрана»: tugma, aylanish, pastki «wallbar» (asboblar yashirin bo'lgani uchun portal). */
export function ScreenMode({ menu, route }: { menu: MenuOut; route: Route }) {
  const { active } = useScreenState();
  const sections = useScreenRotation(menu, route);
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)');

  useEffect(() => {
    document.documentElement.classList.toggle('screen-motion', active && !reduced);
    return () => document.documentElement.classList.remove('screen-motion');
  }, [active, reduced]);

  useEffect(() => {
    if (active && route.kind !== 'section') stopScreen();
  }, [active, route.kind]);

  if (sections.length === 0) return null;
  return (
    <>
      <button type="button" className="tool" title={t('screen.buttonTitle')} onClick={startScreen}>
        <Icon name="monitor" />
        <span className="tool__label">{t('screen.button')}</span>
      </button>
      {active
        ? createPortal(
            <div className="wallbar" role="status">
              <span>{t('screen.info')}</span>
              <button type="button" className="wallbar__exit" onClick={stopScreen}>
                {t('screen.exit')}
              </button>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
