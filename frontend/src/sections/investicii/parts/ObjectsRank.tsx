import type { InvObjectOut } from '../../../api/types';
import { formatPct } from '../../../dash/money';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { toggleBranch } from '../../useSection';

/** Prototip «Освоение по объектам»: освоено с начала года, черта — годовой план. */
export function ObjectsRank({ objects, filters, onBranch, className }: { objects: InvObjectOut[]; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('inv.rank.title');
  const byId = new Map(objects.map((o) => [o.object_id, o]));
  return (
    <Card className={className} title={title} sub={t('inv.rank.sub')}>
      <Rank
        label={title}
        items={objects.map((o) => ({ id: o.object_id, name: o.name, value: o.fact_ytd, mark: o.plan_year, note: t('inv.rank.note', { pct: formatPct(o.plan_year > 0 ? o.fact_ytd / o.plan_year : null, 0) }) }))}
        onSelect={(id) => {
          const o = byId.get(Number(id));
          if (o) toggleBranch(filters, o.branch_id, onBranch);
        }}
        activeId={null}
      />
    </Card>
  );
}
