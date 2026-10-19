import type { ReactNode } from 'react';
import { t } from '../i18n';
import { LogoMark } from '../shell/TopBar';
import { cx } from '../ui/cx';
import { Icon } from '../ui/icons';
import './auth.css';

export function AuthLayout({ children, wide = false, footer }: { children: ReactNode; wide?: boolean; footer?: ReactNode }) {
  return (
    <div className="auth">
      <header className="auth__brand">
        <LogoMark className="auth__mark" />
        <span>
          <b className="auth__word">
            UGE<span>KAZNA</span>
          </b>
          <span className="auth__tag">{t('app.tagline')}</span>
        </span>
      </header>
      <main className={cx('auth__card', wide && 'auth__card--wide')}>{children}</main>
      <footer className="auth__foot">{footer ?? t('auth.securityNote')}</footer>
    </div>
  );
}

export function AuthAlert({ message }: { message: string }) {
  return (
    <p className="form-error" role="alert">
      <Icon name="alert" />
      <span>{message}</span>
    </p>
  );
}
