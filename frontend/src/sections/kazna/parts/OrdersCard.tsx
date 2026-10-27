import type { OrderStatusOut } from '../../../api/types';
import { formatMoney } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

const COLORS = ['#c3d7ee', '#9dc0e8', '#5fd0e0', '#2f8ef5', '#0b4fa8', 'var(--neg)'];

export function OrdersCard({ orders, className }: { orders: OrderStatusOut[]; className?: string }) {
  const count = orders.reduce((s, o) => s + o.count, 0);
  const amount = orders.reduce((s, o) => s + o.amount, 0);
  return (
    <Card className={className} title={t('kazna.orders.title')} sub={t('kazna.orders.sub')}>
      {count === 0 ? (
        <p className="note">{t('kazna.orders.none')}</p>
      ) : (
        <>
          <div className="bigline">
            <b>{formatNumber(count)}</b>
            <span>{formatMoney(amount)}</span>
          </div>
          <div className="pipe" aria-hidden="true">
            {orders.map((o, i) => (o.count ? <div key={o.status} style={{ flexGrow: o.count, background: COLORS[i] }} /> : null))}
          </div>
          <ul className="st-list">
            {orders.map((o, i) => (
              <li key={o.status}>
                <i style={{ background: COLORS[i] }} aria-hidden="true" />
                <span>{o.status.charAt(0).toUpperCase() + o.status.slice(1)}</span>
                <b>{formatNumber(o.count)}</b>
                <small>{formatMoney(o.amount)}</small>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
