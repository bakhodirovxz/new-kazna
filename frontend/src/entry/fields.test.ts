import { describe, expect, it } from 'vitest';
import { fromInput, serverErrorText, toInput, unitLabel } from './fields';
import type { EntryField } from './api';

const f = (over: Partial<EntryField>): EntryField => ({
  name: 'x', kind: 'money', title: 'X', required: true, options: [], unit: '', ...over,
});

describe('fromInput', () => {
  it('normalizes ruble-style money', () => {
    expect(fromInput(f({}), '12 345,67')).toEqual({ value: '12345.67' });
    expect(fromInput(f({}), '−5,5')).toEqual({ value: '-5.5' });
  });

  it('rejects ambiguous thousands and extra scale', () => {
    expect(fromInput(f({}), '1,234')).toEqual({ error: 'entry.err.scale', n: 2 });
    expect(fromInput(f({}), '1e5')).toEqual({ error: 'entry.err.number' });
    expect(fromInput(f({}), 'abc')).toEqual({ error: 'entry.err.number' });
  });

  it('checks required and bounds', () => {
    expect(fromInput(f({}), ' ')).toEqual({ error: 'entry.err.required' });
    expect(fromInput(f({ required: false }), '')).toEqual({ value: null });
    expect(fromInput(f({ lo: '0' }), '-1')).toEqual({ error: 'entry.err.range' });
  });

  it('converts percent to ratio and month to first day', () => {
    expect(fromInput(f({ kind: 'pct', lo: '0', hi: '1' }), '12,5')).toEqual({ value: '0.125' });
    expect(fromInput(f({ kind: 'pct', lo: '0', hi: '1' }), '120')).toEqual({ error: 'entry.err.range' });
    expect(fromInput(f({ kind: 'month' }), '2026-09')).toEqual({ value: '2026-09-01' });
    expect(fromInput(f({ kind: 'month' }), '2026-13')).toEqual({ error: 'entry.err.month' });
    expect(fromInput(f({ kind: 'date' }), '2026-09-30')).toEqual({ value: '2026-09-30' });
    expect(fromInput(f({ kind: 'date' }), '30.09.2026')).toEqual({ error: 'entry.err.date' });
  });

  it('strips spaces from secrets', () => {
    expect(fromInput(f({ kind: 'secret' }), '2020 8000 1234 5678 9012')).toEqual({ value: '20208000123456789012' });
  });
});

describe('toInput / helpers', () => {
  it('formats for inputs', () => {
    expect(toInput(f({}), '1500.50')).toBe('1500,50');
    expect(toInput(f({ kind: 'pct' }), '0.125')).toBe('12,5');
    expect(toInput(f({ kind: 'month' }), '2026-09-01')).toBe('2026-09');
    expect(toInput(f({ kind: 'text' }), null)).toBe('');
    expect(unitLabel(f({ kind: 'pct' }))).toBe('%');
    expect(unitLabel(f({ unit: 'млн сум' }))).toBe('млн сум');
  });

  it('maps server codes to Russian', () => {
    expect(serverErrorText('period_locked')).toBe('Период закрыт для изменений');
    expect(serverErrorText('???')).toBe('Недопустимое значение');
  });
});
