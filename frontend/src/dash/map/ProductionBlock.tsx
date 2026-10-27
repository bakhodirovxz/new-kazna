import type { StationProductionOut } from '../../api/types';
import { t } from '../../i18n';
import { formatNumber } from '../../i18n/format';
import { cx } from '../../ui/cx';
import { formatKwh } from '../energy';
import { formula } from '../formulas';
import { formatPct } from '../money';

const LOW_PLAN = 0.95; // TZ 6: qizil — reja bajarilishi 95% dan past
const LOW_PAYMENT = 0.85; // TZ 4 qoidasi «Уровень оплаты за энергию < 85%»

/** Prototip `gesPanel` ishlab chiqarish qismi: quvvat, КИУМ, ishlab chiqarish va reja, to'lov darajasi. */
export function ProductionBlock({ capacity, production }: { capacity: number | null; production: StationProductionOut | null }) {
  const execution = production?.execution ?? null;
  const low = execution !== null && execution < LOW_PLAN;
  const payment = production?.payment_level ?? null;
  return (
    <>
      <div className="gp-grid">
        <div title={formula('capacity')}>
          <span>{t('map.capacity')}</span>
          <b>
            {capacity === null ? (
              '—'
            ) : (
              <>
                {formatNumber(capacity)}
                <small>{t('map.mw')}</small>
              </>
            )}
          </b>
        </div>
        <div title={formula('kium')}>
          <span>{t('map.kium')}</span>
          <b>{formatPct(production?.kium ?? null, 1)}</b>
        </div>
      </div>
      {production ? (
        <>
          <div className="gp-line" title={formula('genPlan')}>
            <span>{t('map.generation')}</span>
            <b>
              {formatKwh(production.generation)} <span className={low ? 'neg' : 'muted'}>{t('map.ofPlan', { pct: formatPct(execution, 0) })}</span>
            </b>
          </div>
          <div className="gp-bar" aria-hidden="true">
            <i className={cx(low && 'is-low')} style={{ width: `${Math.min(100, Math.max(0, (execution ?? 0) * 100))}%` }} />
          </div>
          <ul className="gp-rows">
            <li>
              <span>{t('map.plan')}</span>
              <b>{formatKwh(production.plan)}</b>
            </li>
            <li title={formula('paymentLevel')}>
              <span>{t('map.paymentLevel')}</span>
              <b className={payment !== null && payment < LOW_PAYMENT ? 'neg' : undefined}>{formatPct(payment, 1)}</b>
            </li>
          </ul>
        </>
      ) : (
        <p className="note">{t('map.noProduction')}</p>
      )}
    </>
  );
}
