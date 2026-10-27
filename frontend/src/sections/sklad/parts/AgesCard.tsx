import type { AgeBucketOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { formula } from '../../../dash/formulas';
import { Rank } from '../../../dash/Rank';
import { t, type MessageKey } from '../../../i18n';
import { Card } from '../../../ui/Card';

const OLD = new Set(['d181_365', 'gt365']);

/** TZ 4 «Возраст запасов»: до 90, 91–180, 181–365, более 365 дней; «нет даты движения» — только если есть. */
export function AgesCard({ ages, hasAge, className }: { ages: AgeBucketOut[]; hasAge: boolean; className?: string }) {
  const title = t('sklad.age.title');
  const items = ages
    .filter((a) => a.key !== 'unknown' || a.value > 0)
    .map((a) => ({ id: a.key, name: t(`sklad.age.${a.key}` as MessageKey), value: a.value, negative: OLD.has(a.key) }));
  return (
    <Card className={className} title={title} sub={t('sklad.age.sub')}>
      {hasAge ? (
        <div title={formula('stockAge')}>
          <Rank label={title} items={items} />
        </div>
      ) : (
        <NoData kind="source" source={t('sklad.age.source')} />
      )}
    </Card>
  );
}
