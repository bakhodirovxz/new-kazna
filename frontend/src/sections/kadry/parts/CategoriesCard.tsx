import type { HrCategoryOut } from '../../../api/types';
import { COLORS } from '../../../dash/chart';
import { formula } from '../../../dash/formulas';
import { formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

/** Prototip `catCard`: структура персонала по категориям (полоса + список). */
export function CategoriesCard({ categories, className }: { categories: HrCategoryOut[]; className?: string }) {
  const total = categories.reduce((s, c) => s + (c.value ?? 0), 0);
  const shades = [COLORS.v0(), COLORS.v1(), COLORS.v2(), COLORS.prev()];
  const color = (i: number): string => shades[i % shades.length] ?? COLORS.v0();
  return (
    <Card className={className} title={t('kad.cat.title')} sub={t('kad.cat.sub')}>
      <div title={formula('headcount')}>
        <div className="split" aria-hidden="true">
          {categories.map((c, i) => (
            <div key={c.name} className={i === 1 || i === 2 ? 'is-dark' : undefined} style={{ flexGrow: c.value ?? 0, background: color(i) }}>
              {total && c.value !== null && c.value / total > 0.12 ? formatPct(c.value / total, 0) : ''}
            </div>
          ))}
        </div>
        <ul className="vt">
          {categories.map((c, i) => (
            <li key={c.name}>
              <i style={{ background: color(i) }} />
              <span>
                {c.name}
                <small>{t('kad.cat.share', { pct: formatPct(total && c.value !== null ? c.value / total : null, 1) })}</small>
              </span>
              <b>{c.value === null ? t('kad.suppressed') : formatNumber(c.value)}</b>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}
