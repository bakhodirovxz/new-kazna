import type { StationGenOut } from '../../../api/types';
import { formatPct } from '../../../dash/money';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { toggleBranch } from '../../useSection';

/** Prototip «Уровень оплаты по станциям»: tartib serverdan (eng pasti birinchi), < 85% — qizil. */
export function PaymentRank({ stations, filters, onBranch, className }: { stations: StationGenOut[]; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('proizv.pay.title');
  return (
    <Card className={className} title={title} sub={t('proizv.pay.sub')}>
      <Rank
        label={title}
        items={stations.map((s) => ({
          id: s.branch_id,
          name: s.name,
          value: s.paid,
          note: t('proizv.pay.note', { pct: formatPct(s.payment_level, 0) }),
          negative: s.payment_level !== null && s.payment_level < 0.85,
        }))}
        onSelect={(id) => toggleBranch(filters, Number(id), onBranch)}
        activeId={filters.br}
      />
    </Card>
  );
}
