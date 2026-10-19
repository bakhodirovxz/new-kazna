import { t } from '../i18n';
import { Skeleton } from '../ui/Skeleton';
import './shell.css';

/** me/menyu kutilayotganda: qobiq shakli saqlanadi (maket siljimaydi). */
export function ShellSkeleton() {
  return (
    <div className="shell-skel" role="status" aria-live="polite">
      <span className="visually-hidden">{t('common.loading')}</span>
      <div className="topbar topbar--skel" aria-hidden="true" />
      <div className="layout">
        <div className="side side--skel" aria-hidden="true">
          <Skeleton variant="title" />
          <Skeleton variant="row" />
          <Skeleton variant="row" />
          <Skeleton variant="row" />
        </div>
        <div className="main" aria-hidden="true">
          <Skeleton variant="title" />
          <Skeleton variant="card" />
        </div>
      </div>
    </div>
  );
}
