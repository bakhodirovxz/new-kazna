import type { SettingOut } from '../api/types';
import { t } from '../i18n';
import { formatDecimal, parseDecimal } from './numbers';

type Meta = Pick<SettingOut, 'kind' | 'lo' | 'hi' | 'unit'>;
export type Parsed = { ok: true; value: unknown } | { ok: false; error: string };

export function rangeHint(s: Meta): string {
  return t('settings.range', { lo: formatDecimal(s.lo ?? 0), hi: formatDecimal(s.hi ?? 0) });
}

/** Muharrir maydoni uchun matn. */
export function formatSetting(s: Meta, value: unknown): string {
  if (s.kind === 'int' || s.kind === 'float') return typeof value === 'number' ? formatDecimal(value) : '';
  if (s.kind === 'bool') return value === true ? 'true' : 'false';
  if (s.kind === 'list') return Array.isArray(value) ? value.map(String).join('\n') : '';
  if (s.kind === 'json') return JSON.stringify(value, null, 2);
  return typeof value === 'string' ? value : '';
}

/** Jadval uchun qisqa ko'rinish. */
export function displaySetting(s: Meta, value: unknown): string {
  if (s.kind === 'bool') return value === true ? t('common.yes') : t('common.no');
  if (s.kind === 'list') return Array.isArray(value) && value.length ? value.map(String).join(', ') : '—';
  if (s.kind === 'json') {
    const text = JSON.stringify(value);
    return text.length > 80 ? `${text.slice(0, 79)}…` : text;
  }
  const text = formatSetting(s, value);
  if (!text) return '—';
  return s.unit ? `${text} ${s.unit}` : text;
}

export function parseSetting(s: Meta, raw: string): Parsed {
  const text = raw.trim();
  switch (s.kind) {
    case 'int':
    case 'float': {
      const n = parseDecimal(text);
      if (n === null) return { ok: false, error: t('settings.invalidNumber') };
      if (s.kind === 'int' && !Number.isInteger(n)) return { ok: false, error: t('settings.invalidInteger') };
      if ((s.lo !== null && n < s.lo) || (s.hi !== null && n > s.hi)) return { ok: false, error: rangeHint(s) };
      return { ok: true, value: n };
    }
    case 'bool':
      return { ok: true, value: text === 'true' };
    case 'list':
      return { ok: true, value: text.split(/[\n,;]+/).map((x) => x.trim()).filter(Boolean) };
    case 'json':
      try {
        return { ok: true, value: JSON.parse(text) as unknown };
      } catch {
        return { ok: false, error: t('settings.invalidJson') };
      }
    case 'str':
      return { ok: true, value: text }; // bo'sh satr — "o'chirilgan" (masalan smtp.host)
    default:
      return text ? { ok: true, value: text } : { ok: false, error: t('settings.required') };
  }
}
