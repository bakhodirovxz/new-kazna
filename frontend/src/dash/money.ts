import { t } from '../i18n';
import { formatNumber } from '../i18n/format';

/** TZ 4: summalar mln so'mda saqlanadi, birlik avtomatik (млн, млрд, трлн). */
export function moneyParts(mln: number, digits = 1): { value: string; unit: string } {
  const size = Math.abs(mln);
  if (size >= 1_000_000) return { value: formatNumber(mln / 1_000_000, digits), unit: t('dash.unit.trln') };
  if (size >= 1_000) return { value: formatNumber(mln / 1_000, digits), unit: t('dash.unit.bln') };
  return { value: formatNumber(mln, digits), unit: t('dash.unit.mln') };
}

export function formatMoney(mln: number | null | undefined, digits = 1): string {
  if (mln === null || mln === undefined || !Number.isFinite(mln)) return '—';
  const { value, unit } = moneyParts(mln, digits);
  return `${value}\u00a0${unit}`;
}

export function formatPct(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined || !Number.isFinite(ratio)) return '—';
  return `${formatNumber(ratio * 100, digits)}%`;
}

export function yoyRatio(current: number, previous: number | null | undefined): number | null {
  if (previous === null || previous === undefined || previous === 0) return null;
  // |previous| bo'yicha: manfiy bazada ham yaxshilanish musbat (ЧДП −100 → −50 = +50%).
  return (current - previous) / Math.abs(previous);
}

export function formatDelta(ratio: number): string {
  if (!Number.isFinite(ratio)) return '—';
  return `${ratio >= 0 ? '+' : '−'}${formatNumber(Math.abs(ratio) * 100, 1)}%`;
}
