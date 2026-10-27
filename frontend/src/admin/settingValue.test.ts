import { describe, expect, it } from 'vitest';
import { displaySetting, formatSetting, parseSetting } from './settingValue';

const INT = { kind: 'int', lo: 5, hi: 30, unit: 'мин' } as const;

describe('settingValue', () => {
  it('parses numbers with comma decimals and checks the range', () => {
    expect(parseSetting(INT, '20')).toEqual({ ok: true, value: 20 });
    expect(parseSetting(INT, '31')).toEqual({ ok: false, error: 'Допустимо от 5 до 30' });
    expect(parseSetting(INT, '2,5')).toEqual({ ok: false, error: 'Введите целое число' });
    expect(parseSetting({ kind: 'float', lo: 0, hi: 0.01, unit: '' }, '0,005')).toEqual({ ok: true, value: 0.005 });
    expect(parseSetting(INT, 'abc').ok).toBe(false);
  });

  it('handles lists, json, cron and bool', () => {
    const list = { kind: 'list', lo: null, hi: null, unit: '' } as const;
    expect(parseSetting(list, 'a@uge.uz\n b@uge.uz ,')).toEqual({ ok: true, value: ['a@uge.uz', 'b@uge.uz'] });
    expect(formatSetting(list, ['a@uge.uz', 'b@uge.uz'])).toBe('a@uge.uz\nb@uge.uz');
    const json = { kind: 'json', lo: null, hi: null, unit: '' } as const;
    expect(parseSetting(json, '{"a": [1]}')).toEqual({ ok: true, value: { a: [1] } });
    expect(parseSetting(json, '{a')).toEqual({ ok: false, error: 'Некорректный JSON' });
    const cron = { kind: 'cron', lo: null, hi: null, unit: '' } as const;
    expect(parseSetting(cron, '  ')).toEqual({ ok: false, error: 'Заполните значение' });
    const flag = { kind: 'bool', lo: null, hi: null, unit: '' } as const;
    expect(parseSetting(flag, 'true')).toEqual({ ok: true, value: true });
    expect(displaySetting(flag, false)).toBe('Нет');
  });

  it('displays numbers with units and empty values as a dash', () => {
    expect(displaySetting(INT, 30)).toBe('30 мин');
    expect(displaySetting({ kind: 'float', lo: 0, hi: 1, unit: '' }, 0.001)).toBe('0,001');
    expect(displaySetting({ kind: 'str', lo: null, hi: null, unit: '' }, '')).toBe('—');
    expect(displaySetting({ kind: 'list', lo: null, hi: null, unit: '' }, [])).toBe('—');
  });
});
