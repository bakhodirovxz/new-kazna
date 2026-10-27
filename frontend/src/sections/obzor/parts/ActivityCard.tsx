import type { ActivityAmountOut } from '../../../api/types';
import { formatMoney, formatPct } from '../../../dash/money';
import { t, type MessageKey } from '../../../i18n';
import { Card } from '../../../ui/Card';

const COLORS: Record<string, string> = { centralized: 'var(--v0)', operating: 'var(--v1)', investing: 'var(--v2)' };

export function ActivityCard({ activity, className }: { activity: ActivityAmountOut[]; className?: string }) {
  const total = activity.reduce((s, a) => s + a.amount, 0);
  return (
    <Card className={className} title={t('obzor.activity.title')} sub={t('obzor.activity.sub')}>
      <div className="split" aria-hidden="true">
        {activity
          .filter((a) => a.amount > 0)
          .map((a) => (
            <div key={a.activity} style={{ flexGrow: a.amount, background: COLORS[a.activity] }}>
              {total && a.amount / total > 0.08 ? formatPct(a.amount / total, 0) : ''}
            </div>
          ))}
      </div>
      <ul className="vt">
        {activity.map((a) => (
          <li key={a.activity}>
            <i style={{ background: COLORS[a.activity] }} />
            <span>
              {t(`dash.activity.${a.activity}` as MessageKey)}
              <small>{t('obzor.activity.share', { share: formatPct(total ? a.amount / total : null) })}</small>
            </span>
            <b>{formatMoney(a.amount)}</b>
          </li>
        ))}
      </ul>
    </Card>
  );
}
