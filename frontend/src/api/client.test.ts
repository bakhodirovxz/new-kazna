import { describe, expect, it } from 'vitest';
import { apiError, json, mockApi } from '../test/mockApi';
import { api, ApiError, apiUrl, isApiError, readCookie } from './client';

describe('apiUrl', () => {
  it('adds the prefix and skips empty query values', () => {
    expect(apiUrl('/audit', { page: 2, action: 'auth.', user_id: null, result: undefined, q: '' })).toBe(
      '/api/v1/audit?page=2&action=auth.',
    );
    expect(apiUrl('/auth/me')).toBe('/api/v1/auth/me');
  });
});

describe('api', () => {
  it('GETs JSON with same-origin credentials and no CSRF header', async () => {
    document.cookie = '__Host-ugk_csrf=tok123; Secure; Path=/';
    const server = mockApi({ 'GET /auth/me': json({ id: 1 }) });
    await expect(api('/auth/me')).resolves.toEqual({ id: 1 });
    const init = server.fetchMock.mock.calls[0]?.[1];
    expect(init?.credentials).toBe('same-origin');
    expect(server.calls[0]?.headers.get('X-CSRF-Token')).toBeNull();
  });

  it('sends the CSRF token and JSON body on unsafe methods', async () => {
    document.cookie = '__Host-ugk_csrf=tok123; Secure; Path=/';
    expect(readCookie('__Host-ugk_csrf')).toBe('tok123');
    const server = mockApi({ 'PATCH /admin/users/5': json({ ok: true }) });
    await api('/admin/users/5', { method: 'PATCH', body: { full_name: 'А' } });
    expect(server.calls[0]?.headers.get('X-CSRF-Token')).toBe('tok123');
    expect(server.calls[0]?.headers.get('Content-Type')).toBe('application/json');
    expect(server.calls[0]?.body).toEqual({ full_name: 'А' });
  });

  it('returns undefined for 204', async () => {
    mockApi({ 'POST /auth/logout': { status: 204 } });
    await expect(api('/auth/logout', { method: 'POST' })).resolves.toBeUndefined();
  });

  it('turns the error envelope into ApiError', async () => {
    mockApi({ 'POST /admin/users': apiError(409, 'username_taken', 'Логин уже занят', { field: 'username' }) });
    const error = await api('/admin/users', { method: 'POST', body: {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      code: 'username_taken',
      message: 'Логин уже занят',
      requestId: 'req-test',
      params: { field: 'username' },
      retryAfter: null,
    });
    expect(isApiError(error, 409, 'username_taken')).toBe(true);
    expect(isApiError(error, 401)).toBe(false);
  });

  it('reads Retry-After on 429', async () => {
    mockApi({
      'POST /auth/login': apiError(429, 'rate_limited', 'Слишком много запросов', { retry_after: 42 }, { 'Retry-After': '42' }),
    });
    const error = await api('/auth/login', { method: 'POST', body: {} }).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 429, retryAfter: 42 });
  });

  it('handles non-JSON errors and network failures', async () => {
    mockApi({ 'GET /x': { status: 502 } });
    await expect(api('/x')).rejects.toMatchObject({ status: 502, code: 'http_502', message: 'Не удалось выполнить запрос' });
    mockApi({ 'GET /y': () => Promise.reject(new TypeError('Failed to fetch')) });
    await expect(api('/y')).rejects.toMatchObject({ status: 0, code: 'network' });
  });

  it('rethrows aborts untouched', async () => {
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' });
    mockApi({ 'GET /z': () => Promise.reject(abort) });
    await expect(api('/z')).rejects.toBe(abort);
  });
});
