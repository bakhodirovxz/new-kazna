import { t } from '../i18n';
import { formatNumber } from '../i18n/format';

/** Prototip `kwh`: backend mln kVt·soat beradi; 1000 va undan ko'p — «млрд кВт·ч». */
export function kwhParts(mln: number, digits = 1): { value: string; unit: string } {
  if (Math.abs(mln) >= 1000) return { value: formatNumber(mln / 1000, digits), unit: t('unit.bnKwh') };
  return { value: formatNumber(mln, digits), unit: t('unit.mlnKwh') };
}

export function formatKwh(mln: number | null | undefined, digits = 1): string {
  if (mln === null || mln === undefined) return t('dash.noValue');
  const parts = kwhParts(mln, digits);
  return `${parts.value} ${parts.unit}`;
}

export function formatMw(mw: number | null | undefined, digits = 0): string {
  if (mw === null || mw === undefined) return t('dash.noValue');
  return `${formatNumber(mw, digits)} ${t('unit.mw')}`;
}
