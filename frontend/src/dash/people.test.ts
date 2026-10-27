import { describe, expect, it } from 'vitest';
import { t } from '../i18n';
import { formatNumber } from '../i18n/format';
import { formatDays, formatHours, formatPeople, formatPp } from './people';

describe('people, days, hours formats', () => {
  it('formats counts with units and handles missing values', () => {
    expect(formatPeople(1250)).toBe(`${formatNumber(1250)} чел.`);
    expect(formatDays(85)).toBe('85 дн.');
    expect(formatHours(420)).toBe('420 ч');
    expect(formatHours(4.666667, 1)).toBe('4,7 ч');
    expect(formatPp(33)).toBe('33 п.п.');
    expect(formatPeople(null)).toBe(t('dash.noValue'));
    expect(formatDays(undefined)).toBe(t('dash.noValue'));
  });
});
