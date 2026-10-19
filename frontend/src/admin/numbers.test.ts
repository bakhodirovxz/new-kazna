import { expect, it } from 'vitest';
import { formatDecimal, parseDecimal } from './numbers';

it('parses decimals with comma or dot and rejects garbage', () => {
  expect(parseDecimal('0,08')).toBe(0.08);
  expect(parseDecimal(' 1.5 ')).toBe(1.5);
  expect(parseDecimal('−0,2')).toBe(-0.2);
  expect(parseDecimal('')).toBeNull();
  expect(parseDecimal('1,2,3')).toBeNull();
  expect(parseDecimal('abc')).toBeNull();
});

it('formats decimals with a comma and no trailing zeros', () => {
  expect(formatDecimal(0.08)).toBe('0,08');
  expect(formatDecimal(1)).toBe('1');
  expect(formatDecimal(-0.25)).toBe('-0,25');
});
