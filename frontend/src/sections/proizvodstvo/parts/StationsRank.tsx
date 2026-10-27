import type { StationGenOut } from '../../../api/types';
import { formatKwh } from '../../../dash/energy';
import { formatPct } from '../../../dash/money';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { buildHash } from '../../../router/hash';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { toggleBranch } from '../../useSection';

/** Prototip `stItems`: выработка по станциям, черта — план, < 95% — qizil; bosish — filial tanlash. */
export function StationsRank({ stations, filters, onBranch, className }: { stations: StationGenOut[]; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('proizv.rank.title');
  return (
    <Card className={className} title={title} sub={t('proizv.rank.sub')}>
      <Rank
        label={title}
        items={stations.map((s) => ({
          id: s.branch_id,
          name: s.name,
          value: s.generation,
          mark: s.plan,
          note: t('proizv.rank.ofPlan', { pct: formatPct(s.execution, 0) }),
          negative: s.execution !== null && s.execution < 0.95,
        }))}
        format={(v) => formatKwh(v)}
        onSelect={(id) => toggleBranch(filters, Number(id), onBranch)}
        activeId={filters.br}
      />
      {filters.br === null ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'proizvodstvo', page: 'stancii', br: null, per: filters.per })}>
          {t('proizv.rank.all')}
        </a>
      ) : null}
    </Card>
  );
}
