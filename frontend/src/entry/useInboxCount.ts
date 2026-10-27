import { useBatches } from './api';

/** Chap menyu hisoblagichi: «На согласовании» (fon so'rovi — sessiya idle'ini surmaydi). */
export function useInboxCount(enabled: boolean): number | undefined {
  const query = useBatches('inbox', 'submitted', { background: true, enabled });
  return enabled ? query.data?.total : undefined;
}
