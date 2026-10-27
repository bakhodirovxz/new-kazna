import { t, type MessageKey } from '../i18n';

export function monthShort(monthId: number): string {
  return t(`dash.m${monthId % 100}` as MessageKey);
}
