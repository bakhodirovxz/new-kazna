import { keepPreviousData, MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';
import { t } from '../i18n';
import { ApiError } from './client';

interface AppMeta extends Record<string, unknown> {
  /** true — global ishlov (redirect/toast) o'tkazib yuboriladi; komponent o'zi ko'rsatadi. */
  silent?: boolean;
}

declare module '@tanstack/react-query' {
  interface Register {
    queryMeta: AppMeta;
    mutationMeta: AppMeta;
  }
}

export interface GlobalErrorHooks {
  onUnauthenticated(): void;
  onPasswordChange(): void;
  onForbidden(): void;
  notify(message: string): void;
}

/** Spec 8: 401 → login; 403 password_change_required → parol; 403 → нет доступа / toast; 429 → toast. */
export function handleApiError(error: unknown, kind: 'query' | 'mutation', hooks: GlobalErrorHooks): void {
  if (!(error instanceof ApiError)) return;
  if (error.status === 401) {
    hooks.onUnauthenticated();
    return;
  }
  if (error.status === 403 && error.code === 'password_change_required') {
    hooks.onPasswordChange();
    return;
  }
  if (error.status === 429) {
    hooks.notify(t('error.rateLimited', { seconds: error.retryAfter ?? 60 }));
    return;
  }
  if (error.status === 403) {
    if (kind === 'query') hooks.onForbidden();
    else hooks.notify(error.message);
  }
}

function shouldRetry(failureCount: number, error: Error): boolean {
  if (failureCount >= 2) return false;
  if (error instanceof ApiError) return error.status === 0 || error.status >= 500;
  return true;
}

export function createQueryClient(hooks: GlobalErrorHooks): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (!query.meta?.silent) handleApiError(error, 'query', hooks);
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (!mutation.meta?.silent) handleApiError(error, 'mutation', hooks);
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 5 * 60_000,
        placeholderData: keepPreviousData,
        refetchOnWindowFocus: false,
        retry: shouldRetry,
      },
      mutations: { retry: false },
    },
  });
}
