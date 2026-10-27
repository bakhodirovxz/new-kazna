import { t, type MessageKey } from '../i18n';

/** TZ 6 «Оформление»: каждый показатель имеет подсказку с формулой из раздела 4. */
export type IndicatorKey =
  | 'opening' | 'inflow' | 'outflow' | 'net' | 'closing' | 'diff' | 'yoy' | 'planExecution' | 'deviation'
  | 'orders' | 'requests' | 'receivable' | 'payable' | 'overdue' | 'calendar' | 'coverage' | 'targetUse' | 'balance'
  | 'generation' | 'genPlan' | 'capacity' | 'kium' | 'ownNeeds' | 'supply' | 'paymentLevel' | 'currentPower'
  | 'stockValue' | 'turnover' | 'belowMin' | 'illiquid' | 'stockAge' | 'stockFlow';

export function formula(key: IndicatorKey): string {
  return t(`formula.${key}` as MessageKey);
}
