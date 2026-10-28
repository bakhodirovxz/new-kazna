import type { FinBaseOut } from '../../../api/types';
import { formatMoney } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate, formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

/** Model kirishlari va ogohlantirishlar: eskirgan допущения, qisqa tarix, kurs yo'q, АИП yo'q. */
export function BaseInfoCard({ base, className }: { base: FinBaseOut; className?: string }) {
  const warnings = [
    base.stale_assumptions ? t('fm.base.stale') : null,
    base.opex_months < 12 ? t('fm.base.opexShort', { months: base.opex_months }) : null,
    base.missing_fx.length ? t('fm.base.missingFx', { list: base.missing_fx.join(', ') }) : null,
    base.aip_missing_years.length ? t('fm.base.aipMissing', { years: base.aip_missing_years.join(', ') }) : null,
  ].filter((x): x is string => x !== null);
  return (
    <Card className={className} title={t('fm.base.title')} sub={t('fm.base.sub', { date: formatDate(base.as_of) })}>
      <ul className="fin-base">
        <li><span>{t('fm.base.capacity')}</span><b>{formatNumber(base.capacity_mw, 0)} {t('fm.unit.mw')}</b></li>
        <li><span>{t('fm.base.opex')}</span><b>{formatMoney(base.opex_base)}</b></li>
        <li><span>{t('fm.base.cash')}</span><b>{formatMoney(base.opening_cash)}</b></li>
        <li><span>{t('fm.base.covenant')}</span><b>{formatNumber(base.covenant, 2)}</b></li>
      </ul>
      {warnings.length ? (
        <div role="status">
          <ul className="fin-warn">
            {warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}
