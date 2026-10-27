import { t, type MessageKey } from '../i18n';
import { formatDate, formatNumber } from '../i18n/format';
import { ru } from '../i18n/ru';
import type { EntryField } from './api';

export type FieldResult = { value: string | null } | { error: MessageKey; n?: number };

const SCALE: Record<string, number> = { money: 2, volume: 3, decimal: 3 };

/** Serverdan kelgan qiymat -> kiritish maydoni matni (ruscha vergul, foiz, YYYY-MM). */
export function toInput(field: Pick<EntryField, 'kind'>, value: unknown): string {
  if (value === null || value === undefined) return '';
  const text = String(value);
  switch (field.kind) {
    case 'money':
    case 'volume':
    case 'decimal':
      return text.replace('.', ',');
    case 'pct':
      return String(Number((Number(text) * 100).toFixed(3))).replace('.', ',');
    case 'month':
      return text.slice(0, 7);
    default:
      return text;
  }
}

/** Serverdan kelgan qiymat -> ko'rsatish matni (ДД.ММ.ГГГГ, «1 234,50»); tahrirlash uchun `toInput`. */
export function displayValue(field: Pick<EntryField, 'kind'>, value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  const text = String(value);
  const num = Number(text);
  switch (field.kind) {
    case 'money':
      return Number.isFinite(num) ? formatNumber(num, 2) : text;
    case 'volume':
    case 'decimal':
      return Number.isFinite(num) ? formatNumber(num, 3) : text;
    case 'int':
      return Number.isFinite(num) ? formatNumber(num, 0) : text;
    case 'pct':
      return Number.isFinite(num) ? `${formatNumber(num * 100, 1)}%` : text;
    case 'date':
      return /^\d{4}-\d{2}-\d{2}$/.test(text) ? formatDate(text) : text;
    case 'month':
      return /^\d{4}-\d{2}/.test(text) ? `${text.slice(5, 7)}.${text.slice(0, 4)}` : text;
    default:
      return text;
  }
}

function inRange(field: EntryField, num: number): boolean {
  if (field.lo != null && num < Number(field.lo)) return false;
  if (field.hi != null && num > Number(field.hi)) return false;
  return true;
}

/** Maydon matni -> serverga yuboriladigan kanonik qiymat (satr) yoki xato kaliti. */
export function fromInput(field: EntryField, raw: string): FieldResult {
  const text = raw.trim();
  if (text === '') return field.required ? { error: 'entry.err.required' } : { value: null };
  switch (field.kind) {
    case 'money':
    case 'volume':
    case 'decimal':
    case 'pct': {
      const norm = text.replace(/\s/g, '').replace('−', '-').replace(',', '.');
      if (!/^-?\d+(\.\d+)?$/.test(norm)) return { error: 'entry.err.number' };
      if (field.kind === 'pct') {
        const ratio = Number(norm) / 100;
        return inRange(field, ratio) ? { value: String(Number(ratio.toFixed(5))) } : { error: 'entry.err.range' };
      }
      const scale = SCALE[field.kind] ?? 2;
      if ((norm.split('.')[1] ?? '').length > scale) return { error: 'entry.err.scale', n: scale };
      return inRange(field, Number(norm)) ? { value: norm } : { error: 'entry.err.range' };
    }
    case 'month':
      return /^\d{4}-(0[1-9]|1[0-2])$/.test(text) ? { value: `${text}-01` } : { error: 'entry.err.month' };
    case 'date':
      return /^\d{4}-\d{2}-\d{2}$/.test(text) && !Number.isNaN(Date.parse(text)) ? { value: text } : { error: 'entry.err.date' };
    case 'secret':
      return { value: text.replace(/\s/g, '') };
    default:
      return { value: text };
  }
}

export function unitLabel(field: Pick<EntryField, 'unit' | 'kind'>): string {
  return field.kind === 'pct' ? '%' : field.unit;
}

/** `entry.err.<server kodi>`; noma'lum kod -> umumiy matn. */
export function serverErrorText(code: string): string {
  const key = `entry.err.${code}`;
  return isMessageKey(key) ? t(key) : t('entry.err.invalid_value');
}

function isMessageKey(key: string): key is MessageKey {
  return Object.hasOwn(ru, key);
}
