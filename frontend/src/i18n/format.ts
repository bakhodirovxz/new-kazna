/** Spec 7.7: razryadlar bo'shliq bilan, kasr vergul bilan, ДД.ММ.ГГГГ, Toshkent vaqti. */
export const TIME_ZONE = 'Asia/Tashkent';

const numberFormats = new Map<number, Intl.NumberFormat>();

function numberFormat(digits: number): Intl.NumberFormat {
  let format = numberFormats.get(digits);
  if (!format) {
    format = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: digits, maximumFractionDigits: digits });
    numberFormats.set(digits, format);
  }
  return format;
}

export function formatNumber(value: number, digits = 0): string {
  if (!Number.isFinite(value)) return '—';
  return numberFormat(digits)
    .format(value)
    .replace(/[\u202f\u00a0]/g, '\u00a0')
    .replace(/^-/, '\u2212');
}

const dateFormat = new Intl.DateTimeFormat('ru-RU', {
  timeZone: TIME_ZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});
const timeFormat = new Intl.DateTimeFormat('ru-RU', {
  timeZone: TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

function toDate(value: string | number | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string | number | Date): string {
  const date = toDate(value);
  return date ? dateFormat.format(date) : '—';
}

export function formatDateTime(value: string | number | Date): string {
  const date = toDate(value);
  return date ? `${dateFormat.format(date)} ${timeFormat.format(date)}` : '—';
}

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '—';
  const total = Math.round(ms / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `${hours} ч ${String(minutes).padStart(2, '0')} мин`;
  if (minutes > 0) return `${minutes} мин ${String(seconds).padStart(2, '0')} с`;
  return `${seconds} с`;
}

export function plural(n: number, forms: readonly [string, string, string]): string {
  const mod100 = Math.abs(n) % 100;
  const mod10 = mod100 % 10;
  if (mod100 > 10 && mod100 < 20) return forms[2];
  if (mod10 > 1 && mod10 < 5) return forms[1];
  if (mod10 === 1) return forms[0];
  return forms[2];
}

/** `YYYY-MM-DD` (Toshkent kuni) boshining UTC ISO vaqti; `offsetDays` — kun siljishi. */
export function dayStartIso(date: string, offsetDays = 0): string {
  const start = new Date(`${date}T00:00:00+05:00`);
  return new Date(start.getTime() + offsetDays * 86_400_000).toISOString();
}
