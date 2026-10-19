import { forwardRef, type ReactNode } from 'react';
import type { MenuOut } from '../api/types';
import { t } from '../i18n';
import { buildHash } from '../router/hash';
import { SectionNav, type NavQuery } from './SectionNav';

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 140 140" aria-hidden="true" focusable="false">
      <circle cx="70" cy="70" r="62" fill="none" stroke="#FFFFFF" strokeWidth="8" />
      <circle cx="70" cy="70" r="51" fill="#EEF4FB" />
      <path d="M70 24C70 24 42 58 42 80a28 28 0 0 0 56 0C98 58 70 24 70 24Z" fill="#1565C0" />
      <rect x="56" y="84" width="7" height="14" rx="1.5" fill="#FFFFFF" />
      <rect x="66.5" y="75" width="7" height="23" rx="1.5" fill="#FFFFFF" />
      <rect x="77" y="66" width="7" height="32" rx="1.5" fill="#FFFFFF" />
    </svg>
  );
}

export interface TopBarProps {
  menu: MenuOut;
  activeSection: string | null;
  navQuery?: NavQuery;
  tools?: ReactNode;
}

export const TopBar = forwardRef<HTMLElement, TopBarProps>(function TopBar({ menu, activeSection, navQuery, tools }, ref) {
  return (
    <header ref={ref} className="topbar">
      <a className="logo" href={buildHash({ kind: 'home' })} aria-label={t('shell.logoLabel')}>
        <LogoMark className="logo__mark" />
        <span className="logo__text">
          <b className="logo__word">
            UGE<span>KAZNA</span>
          </b>
          <span className="logo__tag">{t('app.tagline')}</span>
        </span>
      </a>
      <SectionNav menu={menu} activeSection={activeSection} navQuery={navQuery} />
      {tools ? <div className="tools">{tools}</div> : null}
    </header>
  );
});
