import { t } from '../i18n';

export const API_PREFIX = '/api/v1';
export const CSRF_COOKIE = '__Host-ugk_csrf';
export const CSRF_HEADER = 'X-CSRF-Token';
export const BACKGROUND_HEADER = 'X-UGK-Background';
let backgroundMode = false;

/** S5: «Экран» (kiosk) rejimi — barcha so'rovlar fon: server sessiyaning idle muddatini uzaytirmaydi. */
export function setBackgroundMode(on: boolean): void {
  backgroundMode = on;
}

export function backgroundHeaders(): Record<string, string> {
  return backgroundMode ? { [BACKGROUND_HEADER]: '1' } : {};
}

/** Backend imzolangan double-submit: GET/HEAD/OPTIONS dan boshqa har bir so'rovda cookie qiymati sarlavhada. */
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export type Method = 'GET' | 'HEAD' | 'OPTIONS' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
export type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  method?: Method;
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
  /** Fon (polling) so'rovi: server idle muddatini surmaydi — ochiq qolgan tab sessiyani cho'zmasin. */
  background?: boolean;
  /** Xom tana (fayl yuklash): JSON emas, `rawType` Content-Type bilan. */
  raw?: Blob;
  rawType?: string;
  headers?: Record<string, string>;
}

/** Backend `{"error": {code, message, request_id, params?}}` formatidagi xato. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null = null,
    readonly params: Record<string, unknown> = {},
    readonly retryAfter: number | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function isApiError(error: unknown, status?: number, code?: string): error is ApiError {
  return (
    error instanceof ApiError &&
    (status === undefined || error.status === status) &&
    (code === undefined || error.code === code)
  );
}

export function readCookie(name: string): string | null {
  for (const part of document.cookie.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return decodeURIComponent(rest.join('='));
  }
  return null;
}

export function apiUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === null || value === undefined || value === '') continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return `${API_PREFIX}${path}${qs ? `?${qs}` : ''}`;
}

interface ErrorEnvelope {
  error: { code: string; message: string; request_id?: string | null; params?: Record<string, unknown> };
}

function isEnvelope(payload: unknown): payload is ErrorEnvelope {
  if (typeof payload !== 'object' || payload === null || !('error' in payload)) return false;
  const error = (payload as { error: unknown }).error;
  return typeof error === 'object' && error !== null && 'code' in error && 'message' in error;
}

export function toApiError(response: Response, payload: unknown): ApiError {
  const body = isEnvelope(payload) ? payload.error : null;
  const header = response.headers.get('Retry-After');
  const fromParams = body?.params?.retry_after;
  const retryAfter =
    header !== null && /^\d+$/.test(header)
      ? Number(header)
      : typeof fromParams === 'number'
        ? fromParams
        : null;
  return new ApiError(
    response.status,
    body?.code ?? `http_${response.status}`,
    body?.message ?? t('error.generic'),
    body?.request_id ?? null,
    body?.params ?? {},
    retryAfter,
  );
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  const headers: Record<string, string> = { Accept: 'application/json', ...backgroundHeaders() };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (options.raw !== undefined) headers['Content-Type'] = options.rawType ?? 'application/octet-stream';
  Object.assign(headers, options.headers);
  if (options.background) headers[BACKGROUND_HEADER] = '1';
  if (!SAFE_METHODS.has(method)) {
    const token = readCookie(CSRF_COOKIE);
    if (token) headers[CSRF_HEADER] = token;
  }
  let response: Response;
  try {
    response = await fetch(apiUrl(path, options.query), {
      method,
      headers,
      credentials: 'same-origin',
      body: options.raw ?? (options.body === undefined ? undefined : JSON.stringify(options.body)),
      signal: options.signal,
    });
  } catch (error) {
    if ((error as { name?: string } | null)?.name === 'AbortError') throw error;
    throw new ApiError(0, 'network', t('error.network'));
  }
  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json().catch(() => null);
  if (response.ok) return payload as T;
  throw toApiError(response, payload);
}

/** Xom fayl tanasi bilan POST (CSRF `api()` ichida qo'shiladi). */
export function postRaw<T>(path: string, body: Blob, contentType: string, options: RequestOptions = {}): Promise<T> {
  return api<T>(path, { ...options, method: 'POST', raw: body, rawType: contentType });
}

/** Fayl yuklab olish (shablon): xato bo'lsa `ApiError`, aks holda Blob. */
export async function apiBlob(path: string): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), { credentials: 'same-origin', headers: backgroundHeaders() });
  } catch {
    throw new ApiError(0, 'network', t('error.network'));
  }
  if (response.ok) return response.blob();
  throw toApiError(response, await response.json().catch(() => null));
}
