import { describe, expect, it } from 'vitest';
import { formatDelta, formatMoney, formatPct, moneyParts, yoyRatio } from './money';

describe('money', () => {
  it('picks the unit automatically', () => {
    expect(moneyParts(950.26)).toEqual({ value: '950,3', unit: 'млн' });
    expect(formatMoney(1234.5)).toBe('1,2 млрд');
    expect(formatMoney(2_500_000)).toBe('2,5 трлн');
    expect(formatMoney(-12.34)).toBe('−12,3 млн');
    expect(formatMoney(null)).toBe('—');
  });
  it('formats ratios and deltas', () => {
    expect(formatPct(0.8)).toBe('80,0%');
    expect(formatPct(null)).toBe('—');
    expect(yoyRatio(105, 100)).toBeCloseTo(0.05);
    expect(yoyRatio(5, 0)).toBeNull();
    expect(formatDelta(0.052)).toBe('+5,2%');
    expect(formatDelta(-0.031)).toBe('−3,1%');
  });
});
