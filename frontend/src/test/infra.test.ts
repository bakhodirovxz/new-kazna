import { act } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { apiError, json, mockApi } from './mockApi';
import { setViewport } from './viewport';

describe('mockApi', () => {
  it('returns mocked JSON and records the call', async () => {
    const api = mockApi({ 'GET /auth/me': json({ id: 1 }) });
    const response = await fetch('/api/v1/auth/me?x=1');
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ id: 1 });
    expect(api.calls[0]).toMatchObject({ method: 'GET', path: '/auth/me' });
    expect(api.calls[0]?.url.searchParams.get('x')).toBe('1');
  });

  it('passes the parsed body to function handlers', async () => {
    mockApi({ 'POST /auth/login': (req) => json({ echo: req.body }, 200) });
    const response = await fetch('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ a: 1 }) });
    expect(await response.json()).toEqual({ echo: { a: 1 } });
  });

  it('builds the backend error envelope and 204 responses', async () => {
    mockApi({
      'GET /x': apiError(409, 'conflict', 'Конфликт данных'),
      'DELETE /y': { status: 204 },
    });
    const conflict = await fetch('/api/v1/x');
    expect(conflict.status).toBe(409);
    expect(await conflict.json()).toEqual({
      error: { code: 'conflict', message: 'Конфликт данных', request_id: 'req-test' },
    });
    const empty = await fetch('/api/v1/y', { method: 'DELETE' });
    expect(empty.status).toBe(204);
  });

  it('answers unmocked routes with 501', async () => {
    mockApi({});
    const response = await fetch('/api/v1/nope');
    expect(response.status).toBe(501);
  });
});

describe('setViewport', () => {
  it('re-evaluates matchMedia queries and notifies listeners', () => {
    const mql = window.matchMedia('(max-width: 767.98px)');
    const seen: boolean[] = [];
    mql.addEventListener('change', (e) => seen.push(e.matches));
    expect(mql.matches).toBe(false);
    act(() => setViewport(390));
    expect(mql.matches).toBe(true);
    expect(seen).toEqual([true]);
    expect(window.matchMedia('(min-width: 768px) and (max-width: 1279.98px)').matches).toBe(false);
  });
});
