import { describe, expect, it, vi } from 'vitest';
import { ApiError } from './client';
import { createQueryClient, handleApiError, type GlobalErrorHooks } from './queryClient';

function hooks(): GlobalErrorHooks {
  return { onUnauthenticated: vi.fn(), onPasswordChange: vi.fn(), onForbidden: vi.fn(), notify: vi.fn() };
}

describe('handleApiError', () => {
  it('redirects to login on 401', () => {
    const h = hooks();
    handleApiError(new ApiError(401, 'session_expired', 'x'), 'query', h);
    expect(h.onUnauthenticated).toHaveBeenCalledOnce();
  });

  it('sends password_change_required to the password page', () => {
    const h = hooks();
    handleApiError(new ApiError(403, 'password_change_required', 'x'), 'mutation', h);
    expect(h.onPasswordChange).toHaveBeenCalledOnce();
    expect(h.onForbidden).not.toHaveBeenCalled();
  });

  it('shows no-access for query 403 and a toast for mutation 403', () => {
    const h = hooks();
    handleApiError(new ApiError(403, 'scope_violation', 'Нет доступа к данным этого филиала'), 'query', h);
    expect(h.onForbidden).toHaveBeenCalledOnce();
    handleApiError(new ApiError(403, 'csrf_failed', 'Запрос отклонён'), 'mutation', h);
    expect(h.notify).toHaveBeenCalledWith('Запрос отклонён');
  });

  it('notifies about 429 with the retry time', () => {
    const h = hooks();
    handleApiError(new ApiError(429, 'rate_limited', 'x', null, {}, 30), 'query', h);
    expect(h.notify).toHaveBeenCalledWith('Слишком много запросов. Повторите через 30 с.');
  });

  it('leaves validation, conflicts, server and network errors to the component', () => {
    const h = hooks();
    for (const status of [0, 404, 409, 422, 500]) handleApiError(new ApiError(status, 'x', 'x'), 'query', h);
    handleApiError(new Error('plain'), 'query', h);
    expect(h.onUnauthenticated).not.toHaveBeenCalled();
    expect(h.onForbidden).not.toHaveBeenCalled();
    expect(h.notify).not.toHaveBeenCalled();
  });
});

describe('createQueryClient', () => {
  it('routes query errors through the hooks unless meta.silent is set', async () => {
    const h = hooks();
    const client = createQueryClient(h);
    const fail = () => Promise.reject(new ApiError(401, 'unauthenticated', 'x'));
    await client.fetchQuery({ queryKey: ['silent'], queryFn: fail, retry: false, meta: { silent: true } }).catch(() => undefined);
    expect(h.onUnauthenticated).not.toHaveBeenCalled();
    await client.fetchQuery({ queryKey: ['loud'], queryFn: fail, retry: false }).catch(() => undefined);
    expect(h.onUnauthenticated).toHaveBeenCalledOnce();
  });

  it('uses the spec cache defaults and retries only transient errors', () => {
    const client = createQueryClient(hooks());
    const defaults = client.getDefaultOptions().queries;
    expect(defaults?.staleTime).toBe(5 * 60_000);
    const retry = defaults?.retry as (count: number, error: Error) => boolean;
    expect(retry(0, new ApiError(503, 'x', 'x'))).toBe(true);
    expect(retry(0, new ApiError(0, 'network', 'x'))).toBe(true);
    expect(retry(2, new ApiError(503, 'x', 'x'))).toBe(false);
    expect(retry(0, new ApiError(403, 'forbidden', 'x'))).toBe(false);
  });
});
