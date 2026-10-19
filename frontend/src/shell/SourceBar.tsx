import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { useFreshness } from '../meta/api';
import { cx } from '../ui/cx';

/** Prototip-v2 `.srcbar` (2026-10-19 ruling): ma'lumot manbasi va yangiligi, eskirgan bo'lsa — warn. */
export function SourceBar() {
  const { data } = useFreshness();
  if (!data) return null;
  return (
    <div className={cx('srcbar', data.stale ? 'warn' : 'live')}>
      <b>{data.stale ? t('src.stale') : t('src.live')}</b>
      <span>
        {data.last_success_at ? t('src.updated', { time: formatDateTime(data.last_success_at) }) : t('src.never')}
      </span>
      {data.active_build_id !== null ? <span>{t('src.build', { id: data.active_build_id })}</span> : null}
      {data.stale ? <span className="neg">{t('src.staleHint', { hours: data.max_age_hours })}</span> : null}
    </div>
  );
}
