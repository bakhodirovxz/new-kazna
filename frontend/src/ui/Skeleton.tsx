import { t } from '../i18n';
import { cx } from './cx';
import './display.css';

export type SkeletonVariant = 'line' | 'title' | 'kpi' | 'card' | 'row';

export function Skeleton({ variant = 'line', className }: { variant?: SkeletonVariant; className?: string }) {
  return <span className={cx('skel', `skel--${variant}`, className)} aria-hidden="true" />;
}

/** Sahifa kontenti yuklanmoqda: kartalar va jadval shaklida, maket siljimaydi (TZ 6 «Загрузка»). */
export function PageSkeleton() {
  return (
    <div className="page-skel" role="status" aria-live="polite">
      <span className="visually-hidden">{t('common.loading')}</span>
      <div className="page-skel__kpis">
        <Skeleton variant="kpi" />
        <Skeleton variant="kpi" />
        <Skeleton variant="kpi" />
      </div>
      <Skeleton variant="card" />
      <Skeleton variant="row" />
      <Skeleton variant="row" />
      <Skeleton variant="row" />
    </div>
  );
}
