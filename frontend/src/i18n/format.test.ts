import { describe, expect, it } from 'vitest';
import { dayStartIso, formatDate, formatDateTime, formatDuration, formatNumber, plural } from './format';

const NBSP = '\u00a0';

describe('formatNumber', () => {
  it('groups thousands with a no-break space and uses a decimal comma', () => {
    expect(formatNumber(1234567.891, 1)).toBe(`1${NBSP}234${NBSP}567,9`);
    expect(formatNumber(0)).toBe('0');
  });
  it('uses a typographic minus and handles non-finite values', () => {
    expect(formatNumber(-1500, 0)).toBe(`−1${NBSP}500`);
    expect(formatNumber(Number.NaN)).toBe('—');
  });
});

describe('dates', () => {
  it('formats in Tashkent time as ДД.ММ.ГГГГ', () => {
    expect(formatDate('2026-09-23T20:30:00Z')).toBe('24.09.2026');
    expect(formatDate('2026-09-24')).toBe('24.09.2026');
    expect(formatDateTime('2026-09-24T05:07:00Z')).toBe('24.09.2026 10:07');
    expect(formatDate('garbage')).toBe('—');
  });
  it('builds Tashkent day boundaries in ISO UTC', () => {
    expect(dayStartIso('2026-09-24')).toBe('2026-09-23T19:00:00.000Z');
    expect(dayStartIso('2026-09-24', 1)).toBe('2026-09-24T19:00:00.000Z');
  });
});

describe('formatDuration', () => {
  it('renders seconds, minutes and hours', () => {
    expect(formatDuration(45_000)).toBe('45 с');
    expect(formatDuration(125_000)).toBe('2 мин 05 с');
    expect(formatDuration(3_780_000)).toBe('1 ч 03 мин');
    expect(formatDuration(-1)).toBe('—');
  });
});

describe('plural', () => {
  it('picks Russian plural forms', () => {
    const forms = ['код', 'кода', 'кодов'] as const;
    expect(plural(1, forms)).toBe('код');
    expect(plural(3, forms)).toBe('кода');
    expect(plural(5, forms)).toBe('кодов');
    expect(plural(11, forms)).toBe('кодов');
    expect(plural(21, forms)).toBe('код');
  });
});
