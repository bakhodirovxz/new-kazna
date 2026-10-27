import type { ZakNamedOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip «Поставщики» / «Предметы закупок»: сумма договоров за период. */
export function NamedRankCard({ title, sub, rows, className }: { title: string; sub: string; rows: ZakNamedOut[]; className?: string }) {
  return (
    <Card className={className} title={title} sub={sub}>
      {rows.length ? (
        <Rank label={title} items={rows.map((r) => ({ id: r.name, name: r.name, value: r.amount, note: t('zak.suppliers.count', { count: r.count }) }))} />
      ) : (
        <NoData kind="period" />
      )}
    </Card>
  );
}
