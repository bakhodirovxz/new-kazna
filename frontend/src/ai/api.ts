import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { api } from '../api/client';
import type { AiStatusOut } from '../api/types';

/** Funksiya yoqilganmi (sozlama + provayder). Xato jimgina — tugma shunchaki ko'rinmaydi. */
export function useAiStatus(enabled: boolean): UseQueryResult<AiStatusOut> {
  return useQuery({
    queryKey: ['ai', 'status'],
    queryFn: ({ signal }) => api<AiStatusOut>('/ai/status', { signal }),
    enabled,
    staleTime: 5 * 60_000,
    meta: { silent: true },
  });
}
