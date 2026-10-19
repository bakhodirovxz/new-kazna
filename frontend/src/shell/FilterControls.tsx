import { t } from '../i18n';
import { Select } from '../ui/Select';
import type { FiltersApi } from './useFilters';

export function FilterControls({ filters }: { filters: FiltersApi }) {
  const branchOptions = [
    { value: 'all', label: t('filters.allBranches') },
    ...filters.branches.map((b) => ({ value: String(b.id), label: b.name })),
  ];
  const periodOptions = filters.periods.map((p) => ({ value: p.code, label: p.label }));
  return (
    <>
      <Select
        label={t('filters.branch')}
        value={filters.state.br === null ? 'all' : String(filters.state.br)}
        options={branchOptions}
        disabled={filters.locked || !filters.ready}
        icon={filters.locked ? 'lock' : undefined}
        hint={filters.locked ? t('filters.lockedHint') : undefined}
        onChange={(value) => filters.setBranch(value === 'all' ? null : Number(value))}
      />
      <Select
        label={t('filters.period')}
        value={filters.state.per}
        options={periodOptions}
        disabled={!filters.ready}
        onChange={filters.setPeriod}
      />
    </>
  );
}
