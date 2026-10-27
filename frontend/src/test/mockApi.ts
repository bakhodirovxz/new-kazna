import { vi } from 'vitest';

export interface MockRequest {
  method: string;
  path: string;
  url: URL;
  body: unknown;
  headers: Headers;
}

export interface MockResponse {
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
  /** JSON o'rniga xom tana (masalan, SSE oqimi). */
  raw?: BodyInit;
}

export type MockHandler = MockResponse | ((req: MockRequest) => MockResponse | Promise<MockResponse>);

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): MockResponse {
  return { status, body, headers };
}

export function apiError(
  status: number,
  code: string,
  message = code,
  params?: Record<string, unknown>,
  headers: Record<string, string> = {},
): MockResponse {
  return {
    status,
    headers,
    body: { error: { code, message, request_id: 'req-test', ...(params ? { params } : {}) } },
  };
}

/** fetch'ni almashtiradi. Kalit: "METHOD /yo'l" (/api/v1 prefiksisiz, query'siz). */
export function mockApi(routes: Record<string, MockHandler>) {
  const calls: MockRequest[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, 'https://ugk.test');
    const method = (init.method ?? 'GET').toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, '');
    const body = typeof init.body === 'string' ? (JSON.parse(init.body) as unknown) : undefined;
    const request: MockRequest = { method, path, url, body, headers: new Headers(init.headers) };
    calls.push(request);
    const handler = routes[`${method} ${path}`];
    const res =
      handler === undefined
        ? apiError(501, 'unmocked', `${method} ${path}`)
        : typeof handler === 'function'
          ? await handler(request)
          : handler;
    const status = res.status ?? 200;
    const hasBody = res.body !== undefined && status !== 204;
    if (res.raw !== undefined) {
      return new Response(res.raw, { status, headers: { ...res.headers } });
    }
    return new Response(hasBody ? JSON.stringify(res.body) : null, {
      status,
      headers: { ...(hasBody ? { 'Content-Type': 'application/json' } : {}), ...res.headers },
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}
