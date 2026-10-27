import { t } from '../../../i18n';
import { EmptyState } from '../../../ui/EmptyState';

/** TZ 5: «При выборе головной организации выводится сообщение, что станций у неё нет». */
export function NoStations() {
  return <EmptyState icon="factory" title={t('proizv.none.title')} text={t('proizv.none.text')} />;
}
