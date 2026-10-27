import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import { apiError, mockApi } from '../test/mockApi';
import { sseController, sseResponse } from '../test/sse';
import { parseFrame, streamAnalysis, type AiEvent } from './stream';

const body = { section: 'obzor', page: 'svod', br: null, per: 'ytd' };

describe('AI SSE client', () => {
  it('parses frames', () => {
    expect(parseFrame('event: start\ndata: {"request_id":5}')).toEqual({ type: 'start', requestId: 5 });
    expect(parseFrame('event: delta\ndata: {"text":"## Итог\\n"}')).toEqual({ type: 'delta', text: '## Итог\n' });
    expect(parseFrame('event: error\ndata: {"code":"ai_timeout","message":"m"}')).toEqual({ type: 'error', code: 'ai_timeout', message: 'm' });
    expect(parseFrame(': keepalive')).toBeNull();
  });

  it('delivers events split across chunks and sends CSRF', async () => {
    const ctrl = sseController();
    const { calls } = mockApi({ 'POST /ai/analyze': sseResponse(ctrl) });
    document.cookie = '__Host-ugk_csrf=tok; Secure; Path=/';
    const got: AiEvent[] = [];
    const done = streamAnalysis(body, (e) => got.push(e), new AbortController().signal);
    ctrl.send('start', { request_id: 1 });
    ctrl.send('delta', { text: 'Привет' });
    ctrl.send('done', { length: 6 });
    ctrl.close();
    await done;
    expect(got).toEqual([{ type: 'start', requestId: 1 }, { type: 'delta', text: 'Привет' }, { type: 'done', length: 6 }]);
    expect(calls[0]?.headers.get('X-CSRF-Token')).toBe('tok');
    expect(calls[0]?.body).toEqual(body);
  });

  it('throws ApiError before the stream (limit) and cancels the reader on abort', async () => {
    mockApi({ 'POST /ai/analyze': apiError(429, 'ai_limit', 'Лимит', { retry_after: 120, scope: 'org' }, { 'Retry-After': '120' }) });
    await expect(streamAnalysis(body, () => undefined, new AbortController().signal)).rejects.toMatchObject({ status: 429, code: 'ai_limit', retryAfter: 120 });
    const ctrl = sseController();
    mockApi({ 'POST /ai/analyze': sseResponse(ctrl) });
    const abort = new AbortController();
    const running = streamAnalysis(body, () => undefined, abort.signal);
    ctrl.send('start', { request_id: 2 });
    await new Promise((r) => setTimeout(r, 0));
    abort.abort();
    await running.catch((error: unknown) => expect(error).not.toBeInstanceOf(ApiError));
    expect(ctrl.cancelled()).toBe(true);
  });
});
