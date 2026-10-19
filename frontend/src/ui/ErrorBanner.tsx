import { ApiError } from '../api/client';
import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { Button } from './Button';
import { Icon } from './icons';
import './display.css';

export interface ErrorBannerProps {
  error: unknown;
  onRetry?(): void;
  /** TanStack `dataUpdatedAt` (ms): 0 — hali muvaffaqiyatli yuklanmagan. */
  lastSuccessAt?: number | null;
  title?: string;
  retrying?: boolean;
}

/** TZ 6 «Ошибка загрузки витрины»: plashka + oxirgi muvaffaqiyatli yuklash vaqti + «Повторить». */
export function ErrorBanner({ error, onRetry, lastSuccessAt, title, retrying }: ErrorBannerProps) {
  const message = error instanceof ApiError ? error.message : t('error.generic');
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div className="error-banner" role="alert">
      <Icon name="alert" className="error-banner__ic" />
      <div className="error-banner__body">
        <p className="error-banner__title">{title ?? t('error.loadFailed')}</p>
        <p className="error-banner__text">{message}</p>
        {lastSuccessAt ? (
          <p className="error-banner__meta">{t('error.lastSuccess', { time: formatDateTime(lastSuccessAt) })}</p>
        ) : null}
        {requestId ? <p className="error-banner__meta">{t('error.requestId', { id: requestId })}</p> : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" icon="refresh" loading={retrying} onClick={onRetry}>
          {t('common.retry')}
        </Button>
      ) : null}
    </div>
  );
}
