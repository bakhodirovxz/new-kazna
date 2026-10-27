import type { NamedAmountOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

export function CategoriesCard({ categories, asOf, className }: { categories: NamedAmountOut[]; asOf: string; className?: string }) {
  const title = t('sklad.cat.title');
  return (
    <Card className={className} title={title} sub={t('sklad.cat.sub', { date: formatDate(asOf) })}>
      {categories.length ? <Rank label={title} items={categories.map((c) => ({ id: c.name, name: c.name, value: c.amount }))} /> : <NoData kind="period" />}
    </Card>
  );
}
