import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { useFreshness } from '../meta/api';
import { cx } from '../ui/cx';
import { Icon } from '../ui/icons';

/** TZ 6 «Данные устарели»: oxirgi yuklash vaqti; chegaradan (6 soat) oshsa — ogohlantirish. */
export function Freshness() {
  const query = useFreshness();
  const data = query.data;
  if (!data) return null;
  const text = data.last_success_at ? t('fresh.at', { time: formatDateTime(data.last_success_at) }) : t('fresh.never');
  return (
    <div
      className={cx('fresh', data.stale && 'fresh--stale')}
      role="status"
      title={data.stale ? t('fresh.staleTitle', { hours: data.max_age_hours }) : undefined}
    >
      <Icon name={data.stale ? 'alert' : 'clock'} />
      <span className="fresh__text">{text}</span>
      {data.stale ? <span className="fresh__warn">{t('fresh.stale')}</span> : null}
    </div>
  );
}
