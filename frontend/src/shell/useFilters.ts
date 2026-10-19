import { useCallback, useEffect, useMemo } from 'react';
import type { BranchOut, MeOut, PeriodOut } from '../api/types';
import { t } from '../i18n';
import { useBranches, usePeriods } from '../meta/api';
import { buildHash, type SectionRoute } from '../router/hash';
import { navigate } from '../router/store';

export interface FilterState {
  br: number | null;
  per: string;
}

export interface FiltersApi {
  state: FilterState;
  branches: BranchOut[];
  periods: PeriodOut[];
  defaultPeriod: string;
  locked: boolean;
  ready: boolean;
  error: unknown;
  retry(): void;
  branchLabel: string;
  periodLabel: string;
  setBranch(br: number | null): void;
  setPeriod(code: string): void;
  resetAll(): void;
  hrefFor(section: string, page: string | null): string;
}

const NO_BRANCHES: BranchOut[] = [];
const NO_PERIODS: PeriodOut[] = [];

/** TZ 6 «Фильтры»: filial va davr URL'da; noto'g'ri qiymatlar `replace` bilan tuzatiladi. */
export function useFilters(route: SectionRoute, me: MeOut): FiltersApi {
  const branchesQuery = useBranches();
  const periodsQuery = usePeriods();
  const branches = branchesQuery.data ?? NO_BRANCHES;
  const periods = periodsQuery.data?.items ?? NO_PERIODS;
  const defaultPeriod = periodsQuery.data?.default ?? 'ytd';
  const ready = branchesQuery.isSuccess && periodsQuery.isSuccess;
  const lockedBranch = me.branch_ids !== null && me.branch_ids.length === 1 ? (me.branch_ids[0] ?? null) : null;

  const br =
    lockedBranch ??
    (route.br !== null && (!branchesQuery.isSuccess || branches.some((b) => b.id === route.br)) ? route.br : null);
  const per =
    route.per !== null && (!periodsQuery.isSuccess || periods.some((p) => p.code === route.per))
      ? route.per
      : defaultPeriod;
  const urlPer = per === defaultPeriod ? null : per;

  useEffect(() => {
    if (!ready) return;
    // navigate bir xil hash'da hech narsa qilmaydi (sikl yo'q); noto'g'ri/begona parametrlar ham tozalanadi
    navigate({ ...route, br, per: urlPer }, { replace: true });
  }, [ready, route, br, urlPer]);

  const go = useCallback(
    (next: { br: number | null; per: string | null }) => navigate({ ...route, br: lockedBranch ?? next.br, per: next.per }),
    [route, lockedBranch],
  );

  const retry = useCallback(() => {
    if (branchesQuery.isError) void branchesQuery.refetch();
    if (periodsQuery.isError) void periodsQuery.refetch();
  }, [branchesQuery, periodsQuery]);

  return useMemo<FiltersApi>(
    () => ({
      state: { br, per },
      branches,
      periods,
      defaultPeriod,
      locked: lockedBranch !== null,
      ready,
      error: branchesQuery.error ?? periodsQuery.error,
      retry,
      branchLabel: br === null ? t('filters.allBranches') : (branches.find((b) => b.id === br)?.name ?? String(br)),
      periodLabel: periods.find((p) => p.code === per)?.label ?? per,
      setBranch: (next) => go({ br: next, per: urlPer }),
      setPeriod: (code) => go({ br, per: code === defaultPeriod ? null : code }),
      resetAll: () => go({ br: null, per: null }),
      hrefFor: (section, page) => buildHash({ kind: 'section', section, page, br, per: urlPer }),
    }),
    [br, per, urlPer, branches, periods, defaultPeriod, lockedBranch, ready, branchesQuery.error, periodsQuery.error, retry, go],
  );
}
