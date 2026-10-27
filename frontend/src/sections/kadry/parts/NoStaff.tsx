import { NoData } from '../../../dash/DataState';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Штат/численность manbasi hali ulanmagan (HR API tashkilot kesimisiz, fayl yuklanmagan). */
export function NoStaff() {
  return (
    <Card>
      <NoData kind="source" source={t('kad.none.source')} />
    </Card>
  );
}
