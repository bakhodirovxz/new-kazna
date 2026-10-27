import type { FundRowOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { formula } from '../../../dash/formulas';
import { Rank } from '../../../dash/Rank';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { toggleBranch } from '../../useSection';

export function FundsBySource({ rows, date, className }: { rows: FundRowOut[]; date: string; className?: string }) {
  return (
    <Card className={className} title={t('kazna.funds.title')} sub={t('kazna.funds.sub', { date: formatDate(date) })}>
      {rows.length === 0 ? (
        <NoData kind="source" source={t('dash.source.funds')} />
      ) : (
        rows.map((f) => (
          <div key={f.key} className="prog" title={formula('targetUse')}>
            <div className="prog__h">
              <span>{f.name}</span>
              <b>{formatPct(f.share, 0)}</b>
            </div>
            <div className="prog__t" aria-hidden="true">
              <i style={{ width: `${Math.min(100, (f.share ?? 0) * 100)}%` }} />
            </div>
            <div className="prog__f">
              <span>{t('kazna.funds.used', { amount: formatMoney(f.used) })}</span>
              <span>{t('kazna.funds.allocated', { amount: formatMoney(f.allocated) })}</span>
            </div>
          </div>
        ))
      )}
    </Card>
  );
}

export function FundsByBranch({ rows, filters, onBranch, className }: { rows: FundRowOut[]; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  return (
    <Card className={className} title={t('kazna.funds.branches')} sub={t('kazna.funds.branchesSub')}>
      {rows.length === 0 ? (
        <NoData kind="source" source={t('dash.source.funds')} />
      ) : (
        <Rank
          label={t('kazna.funds.branches')}
          items={rows.map((f) => ({ id: f.key, name: f.name, value: f.used, note: t('kazna.funds.share', { share: formatPct(f.share, 0) }) }))}
          onSelect={(id) => toggleBranch(filters, Number(id), onBranch)}
          activeId={filters.br}
        />
      )}
    </Card>
  );
}
