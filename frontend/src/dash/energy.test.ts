import { describe, expect, it } from 'vitest';
import { t } from '../i18n';
import { formatKwh, formatMw, kwhParts } from './energy';

describe('energy format', () => {
  it('switches to billions of kWh from 1000 mln', () => {
    expect(formatKwh(1.8)).toBe('1,8 млн кВт·ч');
    expect(formatKwh(2400.5)).toBe('2,4 млрд кВт·ч');
    expect(kwhParts(310)).toEqual({ value: '310,0', unit: 'млн кВт·ч' });
    expect(formatKwh(null)).toBe(t('dash.noValue'));
  });

  it('formats megawatts', () => {
    expect(formatMw(412.5, 1)).toBe('412,5 МВт');
    expect(formatMw(undefined)).toBe(t('dash.noValue'));
  });
});
