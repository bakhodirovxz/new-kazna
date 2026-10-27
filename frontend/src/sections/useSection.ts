import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query';
import { api, type Query } from '../api/client';
import type { FilterState } from '../shell/useFilters';

export function sectionQuery(filters: FilterState, extra?: Query): Query {
  return { br: filters.br ?? undefined, per: filters.per, ...extra };
}

/** Bo'lim sahifasi ma'lumoti: filtrlar kalitda, oldingi natija filtr almashganda ko'rinib turadi (spec 6.2). */
export function useSection<T>(path: string, filters: FilterState, extra?: Query): UseQueryResult<T> {
  return useQuery({
    queryKey: ['section', path, filters.br, filters.per, extra ?? null],
    queryFn: ({ signal }) => api<T>(path, { query: sectionQuery(filters, extra), signal }),
    placeholderData: keepPreviousData,
  });
}

/** TZ 6: filial qatorini bosish — shu filialni tanlaydi, qayta bosish — olib tashlaydi. */
export function toggleBranch(filters: FilterState, id: number, onBranch: (br: number | null) => void): void {
  onBranch(filters.br === id ? null : id);
}
