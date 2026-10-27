import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { AlertCountOut } from '../api/types';
import type { FilterState } from './useFilters';

/** TZ 5/6: «Требует внимания» bandidagi hisoblagich (filtrlar bilan, 0 — ko'rsatilmaydi). */
export function useAttentionCount(enabled: boolean, filters: FilterState): number | undefined {
  const query = useQuery({
    queryKey: ['section', '/obzor/vnimanie/count', filters.br, filters.per],
    queryFn: ({ signal }) => api<AlertCountOut>('/obzor/vnimanie/count', { query: { br: filters.br ?? undefined, per: filters.per }, signal, background: true }),
    enabled,
    meta: { silent: true },
  });
  const count = query.data?.count ?? 0;
  return count > 0 ? count : undefined;
}
