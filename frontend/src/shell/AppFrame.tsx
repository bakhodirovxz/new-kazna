import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { MenuOut } from '../api/types';
import { t } from '../i18n';
import { cx } from '../ui/cx';
import { Drawer } from '../ui/Drawer';
import { FrameContext, type FrameState } from './FrameContext';
import type { NavQuery } from './SectionNav';
import { SideMenu, type SideModel } from './SideMenu';
import { TopBar } from './TopBar';
import { MOBILE_QUERY, TABLET_QUERY, useMediaQuery } from './useMediaQuery';
import './shell.css';

export interface AppFrameProps {
  menu: MenuOut;
  activeSection: string | null;
  side: SideModel | null;
  navQuery?: NavQuery;
  tools?: ReactNode;
  children: ReactNode;
}

/** Spec 7.5: ≥1280 — to'liq; 768–1279 — yig'iladigan chap panel; <768 — chap menyu Drawer'da. */
export function AppFrame({ menu, activeSection, side, navQuery, tools, children }: AppFrameProps) {
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const isTablet = useMediaQuery(TABLET_QUERY);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const topRef = useRef<HTMLElement>(null);
  const hasSide = side !== null;
  const sideVisible = hasSide && !isMobile && !(isTablet && collapsed);
  const activeId = side?.activeId ?? null;

  useLayoutEffect(() => {
    const element = topRef.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const apply = () => document.documentElement.style.setProperty('--top-offset', `${element.offsetHeight}px`);
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setDrawerOpen(false);
  }, [activeId, activeSection]);

  const toggleSide = useCallback(() => {
    if (isMobile) setDrawerOpen(true);
    else setCollapsed((value) => !value);
  }, [isMobile]);

  const frame = useMemo<FrameState>(
    () => ({ isMobile, isTablet, hasSide, sideVisible, toggleSide }),
    [isMobile, isTablet, hasSide, sideVisible, toggleSide],
  );

  return (
    <FrameContext.Provider value={frame}>
      <button type="button" className="skip" onClick={() => document.getElementById('main')?.focus()}>
        {t('common.skipToContent')}
      </button>
      <TopBar ref={topRef} menu={menu} activeSection={activeSection} navQuery={navQuery} tools={tools} />
      <div className={cx('layout', !sideVisible && 'layout--full')}>
        {side && !isMobile ? <SideMenu model={side} id="side" hidden={!sideVisible} /> : null}
        <main id="main" className="main" tabIndex={-1}>
          {children}
        </main>
      </div>
      {side && isMobile ? (
        <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title={side.title}>
          <SideMenu model={side} onNavigate={() => window.setTimeout(() => setDrawerOpen(false), 0)} />
        </Drawer>
      ) : null}
    </FrameContext.Provider>
  );
}
