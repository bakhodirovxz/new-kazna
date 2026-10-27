import { t } from '../../../i18n';
import { EmptyState } from '../../../ui/EmptyState';

/** TZ 6 «Нет объектов у филиала»: пояснение вместо пустых карточек. */
export function NoLoans() {
  return <EmptyState icon="card" title={t('kredity.none.title')} text={t('kredity.none.text')} />;
}
