import { t } from '../../../i18n';
import { EmptyState } from '../../../ui/EmptyState';

/** Prototip `noData('У выбранного филиала нет объектов адресной программы.')`. */
export function NoObjects() {
  return <EmptyState icon="target" title={t('inv.none.title')} text={t('inv.none.text')} />;
}
