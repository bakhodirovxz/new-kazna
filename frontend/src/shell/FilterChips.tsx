import { t } from '../i18n';
import { Button } from '../ui/Button';
import { Chip } from '../ui/Chip';
import type { FiltersApi } from './useFilters';

export function activeFilterCount(filters: FiltersApi): number {
  return (filters.state.br !== null ? 1 : 0) + (filters.state.per !== filters.defaultPeriod ? 1 : 0);
}

/** Sarlavha ostidagi faol filtrlar: × bilan, 2+ olib tashlanadigan bo'lsa «Сбросить всё» (prototip). */
export function FilterChips({ filters }: { filters: FiltersApi }) {
  if (!filters.ready) return null;
  const chips: Array<{ key: string; label: string; value: string; onRemove?: () => void }> = [];
  if (filters.state.br !== null) {
    chips.push({
      key: 'br',
      label: t('filters.branch'),
      value: filters.branchLabel,
      onRemove: filters.locked ? undefined : () => filters.setBranch(null),
    });
  }
  if (filters.state.per !== filters.defaultPeriod) {
    chips.push({ key: 'per', label: t('filters.period'), value: filters.periodLabel, onRemove: () => filters.setPeriod(filters.defaultPeriod) });
  }
  if (chips.length === 0) return null;
  const removable = chips.filter((chip) => chip.onRemove).length;
  return (
    <div className="chips" role="group" aria-label={t('filters.active')}>
      {chips.map((chip) => (
        <Chip key={chip.key} label={chip.label} value={chip.value} onRemove={chip.onRemove} />
      ))}
      {removable > 1 ? (
        <Button variant="secondary" className="chips__reset" onClick={filters.resetAll}>
          {t('filters.resetAll')}
        </Button>
      ) : null}
    </div>
  );
}
