import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '../test/mockApi';
import { api } from '../api/client';
import { makeQueryClient } from './queryClient';

async function fetchAll(client: ReturnType<typeof makeQueryClient>, keys: string[]) {
  await Promise.allSettled(keys.map((k) => client.fetchQuery({ queryKey: [k], queryFn: () => api(`/${k}`) })));
  await Promise.resolve();
}

describe('makeQueryClient session end', () => {
  it('navigates once to login with the canonical current route for N parallel 401s, clearing cache and flow', async () => {
    mockApi({ 'GET /a': apiError(401, 'session_expired'), 'GET /b': apiError(401, 'session_expired'), 'GET /c': apiError(401, 'session_expired') });
    window.history.replaceState(null, '', '#kazna/svod?per=m05&br=3');
    const replace = vi.spyOn(window.history, 'replaceState');
    const clearFlow = vi.fn();
    const client = makeQueryClient(vi.fn(), clearFlow);
    client.setQueryData(['keep'], 1);
    await fetchAll(client, ['a', 'b', 'c']);
    expect(replace).toHaveBeenCalledTimes(1);
    expect(window.location.hash).toBe('#login?next=kazna%2Fsvod%3Fbr%3D3%26per%3Dm05');
    expect(clearFlow).toHaveBeenCalledTimes(1);
    expect(client.getQueryCache().getAll()).toHaveLength(0);
    replace.mockRestore();
  });

  it('does nothing on a login route', async () => {
    mockApi({ 'GET /a': apiError(401, 'invalid_credentials') });
    window.history.replaceState(null, '', '#login');
    const clearFlow = vi.fn();
    const client = makeQueryClient(vi.fn(), clearFlow);
    client.setQueryData(['keep'], 1);
    await fetchAll(client, ['a']);
    expect(clearFlow).not.toHaveBeenCalled();
    expect(client.getQueryData(['keep'])).toBe(1);
    expect(window.location.hash).toBe('#login');
  });
});
