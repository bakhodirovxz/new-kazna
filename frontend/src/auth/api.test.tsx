import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { apiError, json, mockApi } from '../test/mockApi';
import { createQueryClient } from '../api/queryClient';
import { ME_ADMIN } from '../test/fixtures';
import { createTestClient, Providers } from '../test/render';
import { meKey, useChangePassword, useEnrollConfirm, useEnrollStart, useLogin, useLogout, useMe, useRevokeSession, useSessions, useVerifyMfa } from './api';
import { useAuthFlow } from './AuthFlow';
import { destinationAfterSignIn } from './destination';

function setup() {
  const client = createTestClient();
  const wrapper = ({ children }: { children: ReactNode }) => <Providers client={client}>{children}</Providers>;
  return { client, wrapper };
}

describe('auth hooks', () => {
  it('loads the current user', async () => {
    mockApi({ 'GET /auth/me': json(ME_ADMIN) });
    const { wrapper } = setup();
    const { result } = renderHook(() => useMe(), { wrapper });
    await waitFor(() => expect(result.current.data?.username).toBe('admin'));
  });

  it('logs in silently and returns the next step', async () => {
    const server = mockApi({ 'POST /auth/login': json({ next: 'mfa_verify', mfa_token: 't'.repeat(32) }) });
    const { wrapper } = setup();
    const { result } = renderHook(() => useLogin(), { wrapper });
    let next = '';
    await act(async () => {
      next = (await result.current.mutateAsync({ username: 'admin', password: 'x' })).next;
    });
    expect(next).toBe('mfa_verify');
    expect(server.calls[0]?.body).toEqual({ username: 'admin', password: 'x' });
  });

  it('stores the user in the cache after 2FA', async () => {
    mockApi({ 'POST /auth/2fa/verify': json(ME_ADMIN) });
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useVerifyMfa(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ mfa_token: 't'.repeat(32), code: '123456' });
    });
    expect(client.getQueryData(meKey)).toEqual(ME_ADMIN);
  });

  it('logs out to the login page and clears the cache even if the call fails', async () => {
    mockApi({ 'POST /auth/logout': { status: 500 } });
    const { client, wrapper } = setup();
    client.setQueryData(meKey, ME_ADMIN);
    window.history.replaceState(null, '', '#kazna/svod');
    const { result } = renderHook(() => useLogout(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync().catch(() => undefined);
    });
    expect(window.location.hash).toBe('#login');
    await waitFor(() => expect(client.getQueryData(meKey)).toBeUndefined());
  });

  it('lists and revokes own sessions', async () => {
    const sessions = [
      { id: 'a', created_at: '2026-09-24T05:00:00Z', last_seen_at: '2026-09-24T05:30:00Z', ua_summary: 'Chrome · Windows', ip: '10.0.0.5', current: true },
      { id: 'b', created_at: '2026-09-20T05:00:00Z', last_seen_at: '2026-09-21T05:30:00Z', ua_summary: 'Firefox · Linux', ip: null, current: false },
    ];
    const server = mockApi({ 'GET /auth/sessions': json(sessions), 'DELETE /auth/sessions/b': { status: 204 } });
    const { wrapper } = setup();
    const list = renderHook(() => useSessions(), { wrapper });
    await waitFor(() => expect(list.result.current.data).toHaveLength(2));
    const revoke = renderHook(() => useRevokeSession(), { wrapper });
    await act(async () => {
      await revoke.result.current.mutateAsync('b');
    });
    expect(server.calls.map((c) => `${c.method} ${c.path}`)).toContain('DELETE /auth/sessions/b');
  });
});

describe('AuthFlow', () => {
  it('keeps the challenge in memory and the return target after finish', () => {
    const { wrapper } = setup();
    const { result } = renderHook(() => useAuthFlow(), { wrapper });
    act(() => result.current.begin({ mfaToken: 'tok', step: 'mfa_verify', username: 'admin', returnTo: 'kazna/svod?br=3' }));
    expect(result.current.challenge?.mfaToken).toBe('tok');
    act(() => result.current.finish());
    expect(result.current.challenge).toBeNull();
    expect(result.current.returnTo).toBe('kazna/svod?br=3');
    act(() => result.current.clear());
    expect(result.current.returnTo).toBeNull();
    expect(window.sessionStorage.length).toBe(0);
    expect(window.localStorage.length).toBe(0);
  });
});

describe('destinationAfterSignIn', () => {
  it('forces the password page and otherwise returns to the safe target', () => {
    expect(destinationAfterSignIn({ ...ME_ADMIN, must_change_password: true }, 'kazna/svod')).toEqual({ kind: 'password' });
    expect(destinationAfterSignIn(ME_ADMIN, 'kazna/svod?br=3')).toEqual({ kind: 'section', section: 'kazna', page: 'svod', br: 3, per: null });
    expect(destinationAfterSignIn(ME_ADMIN, null)).toEqual({ kind: 'home' });
    expect(destinationAfterSignIn(ME_ADMIN, 'login')).toEqual({ kind: 'home' });
  });
});

describe('auth hooks, security (review round 1)', () => {
  it('drops the previous user cache when a new session is established', async () => {
    mockApi({
      'POST /auth/2fa/verify': json(ME_ADMIN),
      'POST /auth/2fa/enroll/confirm': json({ user: ME_ADMIN, backup_codes: ['aaaa-bbbb'] }),
    });
    const { client, wrapper } = setup();
    client.setQueryData(['meta', 'menu'], { groups: [] });
    client.setQueryData(['meta', 'branches'], [{ id: 3 }]);
    client.setQueryData(['auth', 'sessions'], []);
    const verify = renderHook(() => useVerifyMfa(), { wrapper });
    await act(async () => {
      await verify.result.current.mutateAsync({ mfa_token: 't'.repeat(32), code: '123456' });
    });
    expect(client.getQueryCache().getAll().map((q) => q.queryKey)).toEqual([meKey]);
    client.setQueryData(['meta', 'menu'], { groups: [] });
    const enroll = renderHook(() => useEnrollConfirm(), { wrapper });
    await act(async () => {
      await enroll.result.current.mutateAsync({ mfa_token: 't'.repeat(32), code: '123456' });
    });
    expect(client.getQueryCache().getAll().map((q) => q.queryKey)).toEqual([meKey]);
  });

  it('keeps no secrets in the mutation cache after mutations settle', async () => {
    mockApi({
      'POST /auth/login': json({ next: 'mfa_verify', mfa_token: 'SECRETTOKEN'.padEnd(32, 'x') }),
      'POST /auth/2fa/verify': json(ME_ADMIN),
      'POST /auth/2fa/enroll/start': json({ otpauth_uri: 'otpauth://SECRETURI', qr_svg_data_uri: 'data:x', secret: 'SECRETB32' }),
      'POST /auth/2fa/enroll/confirm': json({ user: ME_ADMIN, backup_codes: ['BACKUPCODE'] }),
      'POST /auth/password/change': { status: 204 },
    });
    const { client, wrapper } = setup();
    const hooks = renderHook(
      () => ({ login: useLogin(), verify: useVerifyMfa(), start: useEnrollStart(), confirm: useEnrollConfirm(), pw: useChangePassword() }),
      { wrapper },
    );
    const tok = 'x'.repeat(32);
    await act(async () => {
      await hooks.result.current.login.mutateAsync({ username: 'admin', password: 'PASSWORD1' });
      await hooks.result.current.verify.mutateAsync({ mfa_token: tok, code: '654321' });
      await hooks.result.current.start.mutateAsync({ mfa_token: tok });
      await hooks.result.current.confirm.mutateAsync({ mfa_token: tok, code: '654321' });
      await hooks.result.current.pw.mutateAsync({ current_password: 'OLDPW', new_password: 'NEWPW' });
    });
    hooks.unmount();
    await waitFor(() => expect(client.getMutationCache().getAll()).toHaveLength(0));
  });

  it('keeps login and 2FA failures silent (no global hook call)', async () => {
    mockApi({
      'POST /auth/login': apiError(401, 'invalid_credentials'),
      'POST /auth/2fa/verify': apiError(401, 'invalid_code'),
    });
    const hooks = { onUnauthenticated: vi.fn(), onPasswordChange: vi.fn(), onForbidden: vi.fn(), notify: vi.fn() };
    const client = createQueryClient(hooks);
    const wrapper = ({ children }: { children: ReactNode }) => <Providers client={client}>{children}</Providers>;
    const { result } = renderHook(() => ({ login: useLogin(), verify: useVerifyMfa() }), { wrapper });
    await act(async () => {
      await result.current.login.mutateAsync({ username: 'a', password: 'b' }).catch(() => undefined);
      await result.current.verify.mutateAsync({ mfa_token: 't'.repeat(32), code: '1' }).catch(() => undefined);
    });
    expect(hooks.onUnauthenticated).not.toHaveBeenCalled();
    expect(hooks.notify).not.toHaveBeenCalled();
  });

  it('clears the AuthFlow state on logout', async () => {
    mockApi({ 'POST /auth/logout': { status: 204 } });
    const { wrapper } = setup();
    const { result } = renderHook(() => ({ flow: useAuthFlow(), logout: useLogout() }), { wrapper });
    act(() => result.current.flow.begin({ mfaToken: 'tok', step: 'mfa_verify', username: 'a', returnTo: 'kazna/svod' }));
    await act(async () => {
      await result.current.logout.mutateAsync();
    });
    expect(result.current.flow.challenge).toBeNull();
    expect(result.current.flow.returnTo).toBeNull();
  });
});
