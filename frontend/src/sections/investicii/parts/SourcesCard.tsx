import type { InvSourceOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `srcCard`: годовой лимит и освоение по источникам финансирования. */
export function SourcesCard({ sources, className }: { sources: InvSourceOut[]; className?: string }) {
  return (
    <Card className={className} title={t('inv.src.title')} sub={t('inv.src.sub')}>
      <div title={formula('invYtd')}>
        {sources.map((s) => (
          <div className="prog" key={s.name}>
            <div className="prog__h">
              <span>{s.name}</span>
              <b>{formatPct(s.share, 0)}</b>
            </div>
            <div className="prog__t" aria-hidden="true">
              <i style={{ width: `${Math.min(100, Math.max(0, (s.share ?? 0) * 100))}%` }} />
            </div>
            <div className="prog__f">
              <span>{t('inv.src.done', { amount: formatMoney(s.fact_ytd) })}</span>
              <span>{t('inv.src.limit', { amount: formatMoney(s.plan_year) })}</span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
