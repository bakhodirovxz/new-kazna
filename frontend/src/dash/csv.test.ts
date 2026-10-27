import { describe, expect, it } from 'vitest';
import { toCsv } from './csv';

describe('toCsv', () => {
  it('writes BOM, semicolons, CRLF and decimal commas', () => {
    const csv = toCsv({ headers: ['Филиал', 'Сумма'], rows: [['Чарвак', 1234.5], ['Итого', null]] });
    expect(csv).toBe('﻿Филиал;Сумма\r\nЧарвак;1234,5\r\nИтого;');
  });
  it('escapes formula-like cells and quotes separators', () => {
    const csv = toCsv({ headers: ['A'], rows: [['=HYPERLINK("x")'], [' +cmd'], ['@SUM(A1)'], ['a;b'], [-5]] });
    const lines = csv.slice(1).split('\r\n');
    expect(lines[1]).toBe('"\'=HYPERLINK(""x"")"');
    expect(lines[2]).toBe("' +cmd");
    expect(lines[3]).toBe("'@SUM(A1)");
    expect(lines[4]).toBe('"a;b"');
    expect(lines[5]).toBe('-5');
  });
});
