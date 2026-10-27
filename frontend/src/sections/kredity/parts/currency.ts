import { t, type MessageKey } from '../../../i18n';

const KNOWN = new Set(['USD', 'EUR', 'CNY', 'UZS']);

/** Prototip `curItems`: «Доллар США (USD)»; noma'lum kod — o'zi. */
export function currencyName(code: string): string {
  return KNOWN.has(code) ? t(`kredity.currency.${code}` as MessageKey) : code;
}
