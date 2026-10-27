import { t } from '../i18n';
import { formatNumber } from '../i18n/format';

function unit(value: number | null | undefined, digits: number, key: 'unit.peopleShort' | 'unit.dayShort' | 'unit.hourShort' | 'unit.pp'): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return t('dash.noValue');
  return `${formatNumber(value, digits)} ${t(key)}`;
}

/** Odamlar soni (S4 «Кадры»): «1 250 чел.». */
export function formatPeople(value: number | null | undefined): string {
  return unit(value, 0, 'unit.peopleShort');
}

/** Kunlar (xarid muddati, avans yoshi): «85 дн.». */
export function formatDays(value: number | null | undefined): string {
  return unit(value, 0, 'unit.dayShort');
}

/** Soatlar (ish vaqtidan tashqari): «420 ч». */
export function formatHours(value: number | null | undefined, digits = 0): string {
  return unit(value, digits, 'unit.hourShort');
}

/** Foiz punktlari (moliyaviy/jismoniy uzilish): «33 п.п.». */
export function formatPp(value: number | null | undefined): string {
  return unit(value, 0, 'unit.pp');
}
