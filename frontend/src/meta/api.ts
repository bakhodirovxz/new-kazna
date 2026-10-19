import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { BranchOut, FreshnessOut, MenuOut, PeriodsOut } from '../api/types';

export const menuKey = ['meta', 'menu'] as const;

export function useMenu(enabled = true) {
  return useQuery({
    queryKey: menuKey,
    queryFn: ({ signal }) => api<MenuOut>('/meta/menu', { signal }),
    enabled,
  });
}

export function useBranches() {
  return useQuery({
    queryKey: ['meta', 'branches'],
    queryFn: ({ signal }) => api<BranchOut[]>('/meta/branches', { signal }),
  });
}

export function usePeriods() {
  return useQuery({
    queryKey: ['meta', 'periods'],
    queryFn: ({ signal }) => api<PeriodsOut>('/meta/periods', { signal }),
  });
}

export function useFreshness() {
  return useQuery({
    queryKey: ['meta', 'freshness'],
    queryFn: ({ signal }) => api<FreshnessOut>('/meta/freshness', { signal }),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });
}
